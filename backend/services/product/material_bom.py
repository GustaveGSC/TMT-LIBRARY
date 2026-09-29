"""物料 BOM（研发 BOM）：导入、展开查看、反查被哪些产品使用。

只收研发 BOM（采购 BOM 只作价格来源，不在这里）。Excel 是多层展开的层次表，
支持 PDM 导出（物料编码+版本）与 ERP 导出（图号）两种格式，表头识别用公共模块
`services.common.bom_excel`。导入时把树拆成「每个有下级的节点一份单层 BOM」存储，查看时逐层展开。

编码对应：研发版本比 ERP 细——成品/产成品 ERP 编码只到 -A，研发是 -A01/-A02；
半成品/原材料 ERP 编码本身就带 -A01。所以按「完整版本 → 仅字母版本 → 无版本」顺序
去 ERP 物料表里找对应编码。

导入是「全有或全无」：任何一行的层次/数量/长度/结构有问题都整份拒绝并列出行号，
不做「猜一个值继续导」（2026-09-27 Codex 评估报告 P0/P1 项）。
"""
import io
import math
import re

from openpyxl import load_workbook
from sqlalchemy import func, or_, tuple_

from database.base import db
from database.models.product.import_raw import ImportProductRaw
from database.models.product.material import MaterialBom, MaterialBomLine, ProductMaterial
from result import Result
from services.common.bom_excel import bom_columns, category_name, numeric_code_text
from services.product import material_bom_price as bom_price
from upload_validation import UploadValidationError
from utils import now_cst


_VERSION_LETTERS_RE = re.compile(r'^([A-Z]+)\d+$')
_LEVEL_RE = re.compile(r'^\d+(\.\d+)*$')
# 展开/反查的最大层数，防止数据里出现环（A 含 B、B 又含 A）时死循环
_MAX_DEPTH = 20
# 研发 BOM 专用行数上限（真实单个产品约 200+ 行），超出直接拒绝，避免大文件长时间占住唯一 worker
MAX_BOM_ROWS = 10000
# 错误信息最多列出的条数
_MAX_ERRORS = 20
# 与模型列宽一致，导入前校验，不靠数据库报错/截断
_FIELD_LIMITS = {'code': 64, 'version': 16, 'name': 255, 'spec': 512, 'category': 64, 'unit': 16}
_FIELD_LABELS = {'code': '编码', 'version': '版本', 'name': '名称', 'spec': '规格',
                 'category': '分类', 'unit': '单位'}
# NUMERIC(14,4) 的整数部分最多 10 位
_MAX_QTY = 10 ** 10


def _drawing(code, version):
    return f'{code}-{version}' if version else code


def _norm(text):
    """编码/版本统一去空格转大写：MySQL ai_ci 不区分大小写，Python 区分，不统一会撞唯一约束。"""
    return str(text or '').strip().upper()


def _is_skipped_code(code):
    """用户 2026-09-27 决定与变更申请单一致：带「.」的 PDM 子零件、14ST10 标准件不进物料 BOM。"""
    return '.' in code or code.startswith('14ST10')


def _parse_level(value, row, errors):
    """层次必须是文本（如 '1.1.10'）。数字单元格里 1.10 已经变成 1.1，无法还原，只能拒绝。"""
    if value is None:
        return ''
    if isinstance(value, bool):
        errors.append(f'第 {row} 行层次无效')
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        errors.append(f'第 {row} 行层次「{value}」是数字格式，请把层次列设为文本后重新导出')
        return None
    text = str(value).strip()
    if text and not _LEVEL_RE.match(text):
        errors.append(f'第 {row} 行层次「{text}」格式不正确')
        return None
    return text


def _parse_qty(value, row, errors):
    """数量必须是大于 0、最多 4 位小数的有限数；空/文本/0/负数都拒绝，不再默认为 1。"""
    try:
        if isinstance(value, bool) or value is None or str(value).strip() == '':
            raise ValueError
        qty = float(value)
    except (TypeError, ValueError):
        errors.append(f'第 {row} 行数量「{value if value is not None else ""}」无效')
        return None
    if not math.isfinite(qty) or qty <= 0 or qty >= _MAX_QTY:
        errors.append(f'第 {row} 行数量「{value}」必须大于 0')
        return None
    if abs(qty * 10000 - round(qty * 10000)) > 1e-6:
        errors.append(f'第 {row} 行数量「{value}」小数超过 4 位')
        return None
    return round(qty, 4)


def _raise_errors(errors):
    if errors:
        more = f'（另有 {len(errors) - _MAX_ERRORS} 处）' if len(errors) > _MAX_ERRORS else ''
        raise UploadValidationError('；'.join(errors[:_MAX_ERRORS]) + more)


def parse_bom_rows(data: bytes):
    """解析研发 BOM Excel，按文件顺序返回行：row/level/code/version/name/spec/category/qty/unit。

    跳过的编码（见 _is_skipped_code）连同它的整个下级一起不要。
    有任何行级错误时汇总后抛 UploadValidationError（带 Excel 行号），不返回部分结果。
    返回 (rows, skipped_count)。
    """
    wb = load_workbook(io.BytesIO(data), data_only=True, read_only=False)
    try:
        ws = wb.active
        if ws.max_row - 1 > MAX_BOM_ROWS:
            raise UploadValidationError(f'BOM 文件最多 {MAX_BOM_ROWS} 行，当前 {ws.max_row - 1} 行')
        format_name, col_map = bom_columns(ws)

        def get(r, name):
            c = col_map.get(name)
            return ws.cell(r, c).value if c else None

        rows, errors = [], []
        skipped = 0
        skip_prefix = None
        for r in range(2, ws.max_row + 1):
            level = _parse_level(get(r, '层次'), r, errors)
            if level is None:
                continue
            if format_name == 'erp':
                drawing = str(get(r, '图号') or '').strip()
                idx = drawing.rfind('-')
                code = drawing[:idx] if idx > 0 else drawing
                version = drawing[idx + 1:] if idx > 0 else ''
                name = str(get(r, '品名') or '').strip()
                spec = str(get(r, '规格') or '').strip()
                category = ''
            else:
                code = numeric_code_text(ws.cell(r, col_map['物料编码']))
                version = str(get(r, '版本') or '').strip()
                category = category_name(get(r, '一级分类'))
                names = [
                    category_name(get(r, col))
                    for col in ('二级分类', '三级分类')
                    if category_name(get(r, col))
                ]
                name = str(get(r, '描述') or '').strip() or '_'.join(names)
                spec = str(get(r, '规格') or '').strip()
            code, version = _norm(code), _norm(version)

            if not level and not code:
                continue          # 空行
            if not level:
                errors.append(f'第 {r} 行缺少层次')
                continue
            if not code:
                errors.append(f'第 {r} 行缺少物料编码')
                continue
            # 跳过的编码：它自己和它下面整棵子树都不要
            if skip_prefix and (level == skip_prefix or level.startswith(skip_prefix + '.')):
                skipped += 1
                continue
            skip_prefix = None
            if _is_skipped_code(code):
                skip_prefix = level
                skipped += 1
                continue

            qty = _parse_qty(get(r, '数量'), r, errors)
            row = {
                'row': r, 'level': level, 'code': code, 'version': version,
                'name': name or None, 'spec': spec or None, 'category': category or None,
                'qty': qty, 'unit': str(get(r, '单位') or '').strip() or None,
            }
            for field, limit in _FIELD_LIMITS.items():
                if row[field] and len(row[field]) > limit:
                    errors.append(f'第 {r} 行{_FIELD_LABELS[field]}超过 {limit} 个字符')
            rows.append(row)
        _raise_errors(errors)
        return rows, skipped
    finally:
        wb.close()


def _line_signature(lines):
    """一次展开的内容签名（子件编码/版本/数量/单位，顺序无关），用于比较重复展开是否一致。"""
    return sorted((l['code'], l['version'], l['qty'], l['unit'] or '') for l in lines)


def build_single_level_boms(rows):
    """把层次行拆成单层 BOM：{(code, version): {'head': row, 'lines': [row]}}。

    结构校验（有问题整份拒绝，带行号）：层次不能重复；非顶层行的上级必须已在它前面出现。
    同一父件在文件里被展开多次（同一半成品挂在多个上级下）时，各次展开内容必须一致才去重，
    不一致直接报错，不再默默取第一次。
    同一父件下同一子件出现多行时合并数量，但单位必须相同、名称/规格/分类不能互相矛盾。
    """
    errors = []
    by_level = {}
    expansions = {}     # 父件 level → {'parent': row, 'lines': {child_key: row}}
    for row in rows:
        level = row['level']
        if level in by_level:
            errors.append(f'第 {row["row"]} 行与第 {by_level[level]["row"]} 行层次重复（{level}）')
            continue
        by_level[level] = row
        dot = level.rfind('.')
        if dot < 0:
            continue
        parent = by_level.get(level[:dot])
        if parent is None:
            errors.append(f'第 {row["row"]} 行（层次 {level}）找不到上级 {level[:dot]}，上级行必须在它前面')
            continue
        exp = expansions.setdefault(parent['level'], {'parent': parent, 'lines': {}})
        child_key = (row['code'], row['version'])
        line = exp['lines'].get(child_key)
        if line is None:
            exp['lines'][child_key] = dict(row)
            continue
        # 同父同子多行：只允许同语义的行相加
        if (line['unit'] or '') != (row['unit'] or ''):
            errors.append(f'第 {line["row"]} 行与第 {row["row"]} 行是同一上级下的同一子件'
                          f' {_drawing(*child_key)}，但单位不同（{line["unit"]} / {row["unit"]}）')
            continue
        for field in ('name', 'spec', 'category'):
            if line[field] and row[field] and line[field] != row[field]:
                errors.append(f'第 {line["row"]} 行与第 {row["row"]} 行是同一子件 {_drawing(*child_key)}，'
                              f'但{_FIELD_LABELS[field]}不一致')
                break
        else:
            if line['qty'] is not None and row['qty'] is not None:
                line['qty'] = round(line['qty'] + row['qty'], 4)
    _raise_errors(errors)

    boms = {}
    for exp in expansions.values():
        parent = exp['parent']
        key = (parent['code'], parent['version'])
        lines = list(exp['lines'].values())
        if key not in boms:
            boms[key] = {'head': parent, 'lines': lines}
            continue
        # 重复展开：内容一致才去重
        first = boms[key]
        if _line_signature(first['lines']) != _line_signature(lines):
            errors.append(f'{_drawing(*key)} 在第 {first["head"]["row"]} 行和第 {parent["row"]} 行'
                          f'各展开了一次，但两处的下级内容不一致')
    _raise_errors(errors)
    return boms


def _order_base_code(code):
    """订单里的成品主件品号 → 研发编码（去掉 -A / -A01 这类版本后缀，统一大写），用于判断订单是否包含本产品。"""
    return re.sub(r'-[A-Za-z]+\d*$', '', (code or '').strip()).upper()


def _erp_info(erp_codes):
    """ERP 物料的名称/规格（一条查询）；BOM 里优先显示 ERP 的，文件里的作兜底。"""
    codes = [c for c in set(erp_codes) if c]
    if not codes:
        return {}
    return {
        r.code: (r.name, r.spec) for r in db.session.query(
            ImportProductRaw.code, ImportProductRaw.name, ImportProductRaw.spec,
        ).filter(ImportProductRaw.code.in_(codes)).all()
    }


def _apply_erp_names(dicts):
    """BOM 表头字典的名称/规格改用 ERP 的（一条查询）：研发 BOM 文件里的名称只有 ERP 名称的前半段
    （如「成品_成人桌类_E时光」，ERP 是「成品_成人桌类_E时光 (V1.2)电动2.0米…_A」），对不上 ERP 时用文件里的兜底。"""
    info = _erp_info([d.get('erp_code') for d in dicts])
    for d in dicts:
        erp_name, erp_spec = info.get(d.get('erp_code'), (None, None))
        d['name'] = erp_name or d.get('name')
        d['spec'] = erp_spec or d.get('spec')
    return dicts


class MaterialBomService:

    # ── 编码对应 ──────────────────────────────────────
    @staticmethod
    def _erp_resolver(pairs):
        """返回 (code, version) → ERP 编码 的函数；候选编码按 1000 个一批查库。

        比较时统一大写，返回 ERP 表里的原始写法。
        """
        candidates = set()
        for code, version in pairs:
            candidates.add(code)
            if version:
                candidates.add(f'{code}-{version}')
                m = _VERSION_LETTERS_RE.match(version)
                if m:
                    candidates.add(f'{code}-{m.group(1)}')
        existing = {}
        cand = list(candidates)
        for i in range(0, len(cand), 1000):
            for (c,) in db.session.query(ImportProductRaw.code).filter(
                ImportProductRaw.code.in_(cand[i:i + 1000])
            ).all():
                existing[c.upper()] = c

        def resolve(code, version):
            code, version = _norm(code), _norm(version)
            if version:
                if f'{code}-{version}' in existing:
                    return existing[f'{code}-{version}']
                m = _VERSION_LETTERS_RE.match(version)
                if m and f'{code}-{m.group(1)}' in existing:
                    return existing[f'{code}-{m.group(1)}']
            return existing.get(code)
        return resolve

    # ── 导入 ──────────────────────────────────────────
    def import_file(self, data: bytes, filename: str, username: str):
        try:
            rows, skipped = parse_bom_rows(data)
            if not rows:
                return Result.fail('文件中没有有效的 BOM 行')
            boms = build_single_level_boms(rows)
        except UploadValidationError as exc:
            return Result.fail(str(exc))
        if not boms:
            return Result.fail('文件中没有带下级的物料，无法生成 BOM')

        pairs = {(r['code'], r['version']) for r in rows}
        resolve = self._erp_resolver(pairs)
        try:
            existing = {
                (b.code.upper(), b.version.upper()): b for b in MaterialBom.query.filter(
                    tuple_(MaterialBom.code, MaterialBom.version).in_(list(boms.keys()))
                ).all()
            }
            now = now_cst()
            created = updated = line_count = 0
            # 覆盖：已有的同版本 BOM 先删掉旧子件行，表头原地更新
            if existing:
                MaterialBomLine.query.filter(
                    MaterialBomLine.bom_id.in_([b.id for b in existing.values()])
                ).delete(synchronize_session=False)
            for key, entry in boms.items():
                head = entry['head']
                bom = existing.get(key)
                if bom is None:
                    bom = MaterialBom(code=head['code'], version=head['version'])
                    db.session.add(bom)
                    created += 1
                else:
                    bom.code, bom.version = head['code'], head['version']
                    updated += 1
                bom.erp_code = resolve(head['code'], head['version'])
                bom.name, bom.spec, bom.category = head['name'], head['spec'], head['category']
                bom.source_file = (filename or '')[:255] or None
                bom.imported_by, bom.imported_at = username, now
                db.session.flush()
                for seq, line in enumerate(entry['lines'], start=1):
                    db.session.add(MaterialBomLine(
                        bom_id=bom.id, seq=seq, code=line['code'], version=line['version'],
                        erp_code=resolve(line['code'], line['version']),
                        name=line['name'], spec=line['spec'], category=line['category'],
                        qty=line['qty'], unit=line['unit'],
                    ))
                    line_count += 1
            db.session.commit()
        except Exception:
            # 服务也可能被脚本/测试直接调用，不能只指望请求结束时的 session 清理
            db.session.rollback()
            raise

        unmatched = sorted({
            _drawing(c, v) for c, v in pairs if resolve(c, v) is None
        })
        roots = [r for r in rows if '.' not in r['level']]
        return Result.ok(data={
            'created': created, 'updated': updated, 'lines': line_count,
            'roots': [_drawing(r['code'], r['version']) for r in roots],
            'unmatched': unmatched, 'skipped': skipped,
        })

    # ── ERP 重导后补关联 ──────────────────────────────
    def relink_unmatched_erp_codes(self):
        """ERP 物料表导入后调用：只给 erp_code 为空的表头/子件行补匹配，已匹配的不重写。"""
        head_rows = db.session.query(MaterialBom.id, MaterialBom.code, MaterialBom.version) \
            .filter(MaterialBom.erp_code.is_(None)).all()
        line_pairs = db.session.query(MaterialBomLine.code, MaterialBomLine.version) \
            .filter(MaterialBomLine.erp_code.is_(None)).distinct().all()
        pairs = {(r.code, r.version) for r in head_rows} | {(c, v) for c, v in line_pairs}
        if not pairs:
            return {'bom_headers_relinked': 0, 'bom_lines_relinked': 0}
        resolve = self._erp_resolver(pairs)
        headers = lines = 0
        try:
            for r in head_rows:
                erp = resolve(r.code, r.version)
                if erp:
                    MaterialBom.query.filter_by(id=r.id).update(
                        {'erp_code': erp}, synchronize_session=False)
                    headers += 1
            for code, version in line_pairs:
                erp = resolve(code, version)
                if erp:
                    lines += MaterialBomLine.query.filter(
                        MaterialBomLine.code == code, MaterialBomLine.version == version,
                        MaterialBomLine.erp_code.is_(None),
                    ).update({'erp_code': erp}, synchronize_session=False)
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        return {'bom_headers_relinked': headers, 'bom_lines_relinked': lines}

    # ── 列表 ──────────────────────────────────────────
    # 列表按「物料类型」分类（与物料表同一套判定：单独指定 > 编码前缀规则 > 分组默认类型），
    # 另有两个兜底分类：unclassified=对应到 ERP 物料但没判出类型，unmatched=对应不到 ERP 物料
    TYPE_KEYS = ('finished', 'packaged', 'semi', 'material', 'useless', 'unclassified', 'unmatched')

    @staticmethod
    def _bom_types(erp_code, by_code):
        if not erp_code:
            return ['unmatched']
        cats = by_code.get(erp_code, ([], None))[0]
        return list(cats) or ['unclassified']

    def list_boms(self, keyword=None, material_type=None, page=1, page_size=50):
        """BOM 列表。分类要用物料类型判定缓存（内存），数据库里没有这一列，所以先取出
        关键词命中的 (id, erp_code) 在内存里分类计数，再按 id 取当前页——共 3 条查询。"""
        from services.product.material import material_service
        q = db.session.query(MaterialBom.id, MaterialBom.erp_code)
        if keyword:
            like = f'%{keyword}%'
            q = q.filter(or_(
                MaterialBom.code.like(like), MaterialBom.erp_code.like(like),
                MaterialBom.name.like(like), MaterialBom.spec.like(like),
            ))
        ordered = q.order_by(MaterialBom.code.asc(), MaterialBom.version.desc()).all()
        by_code = material_service._classification()['by_code']
        types_by_id = {r.id: self._bom_types(r.erp_code, by_code) for r in ordered}

        # 各分类数量（多标签物料，如同时是成品和产成品，两边都计）
        type_counts = {k: 0 for k in self.TYPE_KEYS}
        for types in types_by_id.values():
            for t in types:
                type_counts[t] = type_counts.get(t, 0) + 1

        ids = [r.id for r in ordered
               if not material_type or material_type in types_by_id[r.id]]
        page_ids = ids[(page - 1) * page_size: page * page_size]
        rows = {b.id: b for b in MaterialBom.query.filter(MaterialBom.id.in_(page_ids)).all()}             if page_ids else {}
        counts = dict(
            db.session.query(MaterialBomLine.bom_id, func.count(MaterialBomLine.id))
            .filter(MaterialBomLine.bom_id.in_(page_ids))
            .group_by(MaterialBomLine.bom_id).all()
        ) if page_ids else {}
        return Result.ok(data={
            'items': _apply_erp_names([
                {**rows[i].to_dict(), 'line_count': counts.get(i, 0),
                 'material_types': types_by_id[i]}
                for i in page_ids if i in rows
            ]),
            'total': len(ids), 'all_total': len(ordered),
            'page': page, 'page_size': page_size,
            'type_counts': type_counts,
        })

    def delete_bom(self, bom_id, force=False):
        """硬删除一层 BOM。被其他 BOM 当子件引用时先返回引用它的上级（needs_force），
        前端二次确认后带 force 再删——删掉后这些上级里它会从「可展开」退化成叶子。"""
        bom = db.session.get(MaterialBom, bom_id)
        if bom is None:
            return Result.fail('BOM 不存在')
        if not force:
            parent_ids = [i for (i,) in db.session.query(MaterialBomLine.bom_id).filter(
                MaterialBomLine.code == bom.code, MaterialBomLine.version == bom.version,
            ).distinct().all()]
            if parent_ids:
                parents = MaterialBom.query.filter(MaterialBom.id.in_(parent_ids))                     .order_by(MaterialBom.code, MaterialBom.version).all()
                return Result.fail(
                    f'{_drawing(bom.code, bom.version)} 被 {len(parents)} 个上级 BOM 引用',
                    data={'needs_force': True,
                          'references': [p.to_dict() for p in parents]},
                )
        MaterialBomLine.query.filter_by(bom_id=bom_id).delete(synchronize_session=False)
        db.session.delete(bom)
        db.session.commit()
        return Result.ok()

    # ── 展开 ──────────────────────────────────────────
    def tree(self, bom_id, include_price=False, price_date=None, batch_id=None):
        """展开一份 BOM 的完整多层结构；每层一次查询（O(层数)）。

        include_price=True（调用方已确认 material:price 权限）时给每个节点算单价/金额，价格只多一条查询。
        计价截止点：batch_id（按采购订单，同日多订单也能区分）优先，其次 price_date，都没有 = 最新价格。"""
        root = db.session.get(MaterialBom, bom_id)
        if root is None:
            return Result.fail('BOM 不存在')

        # 逐层把用到的 BOM 和子件行批量取出来
        boms_by_key = {(root.code, root.version): root}
        lines_by_bom = {}
        frontier = [root.id]
        for _ in range(_MAX_DEPTH):
            if not frontier:
                break
            lines = (MaterialBomLine.query.filter(MaterialBomLine.bom_id.in_(frontier))
                     .order_by(MaterialBomLine.bom_id, MaterialBomLine.seq).all())
            for line in lines:
                lines_by_bom.setdefault(line.bom_id, []).append(line)
            child_keys = {(l.code, l.version) for l in lines} - set(boms_by_key)
            if not child_keys:
                break
            found = MaterialBom.query.filter(
                tuple_(MaterialBom.code, MaterialBom.version).in_(list(child_keys))
            ).all()
            for b in found:
                boms_by_key[(b.code, b.version)] = b
            frontier = [b.id for b in found if b.id not in lines_by_bom]

        info = _erp_info(
            [l.erp_code for ls in lines_by_bom.values() for l in ls] + [root.erp_code]
        )

        # 节点 id 按「从根到这一行」的路径生成：同一个半成品在树里出现多次时，
        # 它下面的行也必须是不同的 id（前端表格按 id 区分行、记展开状态）
        def build(bom, path, depth, prefix=''):
            nodes = []
            for line in lines_by_bom.get(bom.id, []):
                key = (line.code, line.version)
                child_bom = boms_by_key.get(key)
                erp_name, erp_spec = info.get(line.erp_code, (None, None))
                node_id = f'{prefix}/{line.id}' if prefix else str(line.id)
                node = {
                    'id': node_id,
                    'code': line.code, 'version': line.version,
                    'drawing': _drawing(line.code, line.version),
                    'erp_code': line.erp_code,
                    'name': erp_name or line.name, 'spec': erp_spec or line.spec,
                    'category': line.category, 'qty': line.qty, 'unit': line.unit,
                    'bom_id': child_bom.id if child_bom else None,
                }
                if child_bom and key not in path and depth < _MAX_DEPTH:
                    node['children'] = build(child_bom, path | {key}, depth + 1, node_id)
                nodes.append(node)
            return nodes

        root_dict = root.to_dict()
        root_name, root_spec = info.get(root.erp_code, (None, None))
        root_dict['name'] = root_name or root.name
        root_dict['spec'] = root_spec or root.spec
        children = build(root, {(root.code, root.version)}, 1)
        if include_price:
            from database.repository.product.material_price import MaterialPriceRepository
            as_of, as_of_label = price_date, price_date.isoformat() if price_date else None
            if batch_id:
                batch = MaterialPriceRepository.batch_cursor(batch_id)
                if batch is None:
                    return Result.fail('采购订单不存在或没有价格')
                as_of = (batch.snapshot_date, batch.max_price_id)
                as_of_label = f"{batch.order_no or '（无订单号）'} · {batch.snapshot_date.isoformat()}"
            histories = bom_price.price_histories(bom_price.collect_codes(children) | {root.code})
            free = self._free_codes(children)
            price = bom_price.root_price(children, root.code, histories, as_of, free=free)
            price.pop('missing_codes', None)
            root_dict.update(price)
            root_dict['priced_as_of'] = as_of_label
        return Result.ok(data={'bom': root_dict, 'children': children})

    # ── 物料卡片：按 BOM 实时计算的价格 + 价格变化历史 ───
    @staticmethod
    def _free_codes(children):
        """树上被标记「不计价」的物料（按 ERP 编码存在 product_material.no_price）→ 基础码集合；一条查询。"""
        pairs = bom_price.collect_pairs(children)
        erps = {erp for _, erp in pairs if erp}
        if not erps:
            return frozenset()
        flagged = {c for (c,) in db.session.query(ProductMaterial.code).filter(
            ProductMaterial.code.in_(list(erps)), ProductMaterial.no_price.is_(True)).all()}
        return frozenset(code for code, erp in pairs if erp in flagged)

    def calc_price(self, erp_code, bom_id=None):
        """物料卡片的「成本视图」（有研发 BOM 的成品/产成品/半成品），全部现算不存库。

        「齐全才计价」（用户 2026-09-28 定）：
        - current：齐全（或有外购价）时给成本，否则 unit_price=None；另给完整度 priced/total（原材料按编码去重）
        - started：开始计价的日期与对应订单（下级价格第一次齐全的那天）；没开始为 None
        - missing_items：缺价的原材料（有效用量、所在部件），没开始计价时用来告诉「卡在哪」
        - composition：齐全时第一层下级金额前 5
        - history：从开始计价那一单往后，按采购订单逐单重算（新→旧），只列成本有变化或包含本产品的订单，
          标出 related（订单成品含本产品或其最终产品；老批次没记录成品为 null）
        """
        from database.models.rd.cost import CostSnapshotSku
        from database.repository.product.material_price import MaterialPriceRepository

        versions = (MaterialBom.query.filter(MaterialBom.erp_code == erp_code)
                    .order_by(MaterialBom.version.desc()).all())
        if not versions:
            return Result.ok(data=None)
        bom = next((b for b in versions if b.id == bom_id), versions[0])
        children = self.tree(bom.id).data['children']
        histories = bom_price.price_histories(bom_price.collect_codes(children) | {bom.code})
        free = self._free_codes(children)
        root_drawing = f'{bom.code}-{bom.version}' if bom.version else bom.code

        now = bom_price.cost_snapshot(children, bom.code, histories, None, root_drawing, free)
        current = bom_price.root_price(children, bom.code, histories, None, annotate=True, free=free)
        current.pop('missing_codes', None)
        current.update({'priced': len(now['covered']), 'total': len(now['leaves'])})
        current['missing'] = current['total'] - current['priced']

        missing_items = sorted((
            {'drawing': v['drawing'], 'erp_code': v['erp_code'], 'name': v['name'],
             'qty': round(v['eq'], 4), 'parents': v['parents']}
            for code, v in now['leaves'].items() if code not in now['covered']
        ), key=lambda x: x['drawing'])

        composition = []
        if current['unit_price']:
            composition = sorted((
                {'drawing': n['drawing'], 'erp_code': n.get('erp_code'), 'name': n.get('name'),
                 'qty': n.get('qty'), 'amount': n.get('amount'),
                 'share': round(n['amount'] / current['unit_price'], 4) if n.get('amount') else 0}
                for n in children if n.get('amount') is not None
            ), key=lambda x: -x['amount'])[:5]

        # 与本物料相关的成品研发编码：自己 + 沿上级找到的最终产品（订单只记录成品主件品号）
        related_codes = {bom.code.upper()}
        for top in self.for_material(erp_code).data['top_products']:
            related_codes.add(top['code'].upper())

        # 旧→新：按计价截止点 (日期, 批次最后一条价格 id) 排，同日多订单按导入先后
        batches = sorted(MaterialPriceRepository.price_batches(), key=lambda b: (b.snapshot_date, b.max_price_id))
        finished_by_batch = {}
        if batches:
            rows = db.session.query(CostSnapshotSku.snapshot_id, CostSnapshotSku.finished_code).filter(
                CostSnapshotSku.snapshot_id.in_([b.id for b in batches])).all()
            for sid, code in rows:
                finished_by_batch.setdefault(sid, set()).add(_order_base_code(code))

        # 开始计价：按 (价格日期, 导入先后) 找第一次齐全的截止点；对应到那次导入的订单
        started, start_cursor, start_sid = bom_price.start_point(children, bom.code, histories, free)
        start_info = None
        if started:
            batch_by_id = {b.id: b for b in batches}
            pick = batch_by_id.get(start_sid)
            start_info = {'date': start_cursor[0].isoformat() if start_cursor else None,
                          'order_no': (pick.order_no or '') if pick else None}

        # 成本历史：每个订单用自己的截止点 (日期, 该订单最后一条价格 id) 重算，同日多个订单也能区分
        history, prev_total = [], None
        if started:
            for b in batches:
                cursor = (b.snapshot_date, b.max_price_id)
                if start_cursor and cursor < start_cursor:
                    continue
                snap = bom_price.cost_snapshot(children, bom.code, histories, cursor, root_drawing, free)
                if not snap['complete']:
                    continue
                related = bool(finished_by_batch.get(b.id, set()) & related_codes)
                known = b.id in finished_by_batch
                if prev_total is None or snap['total'] != prev_total or related:
                    history.append({
                        'batch_id': b.id, 'order_no': b.order_no or '', 'date': b.snapshot_date.isoformat(),
                        'unit_price': snap['total'], 'related': related if known else None,
                        'delta': None if prev_total is None else round(snap['total'] - prev_total, 4),
                    })
                prev_total = snap['total']

        return Result.ok(data={
            'bom': _apply_erp_names([bom.to_dict()])[0],
            'versions': [{'id': b.id, 'drawing': f'{b.code}-{b.version}' if b.version else b.code}
                         for b in versions],
            'current': current,
            'started': start_info,
            'missing_items': missing_items,
            'composition': composition,
            'history': list(reversed(history)),
        })

    # ── 导出 Excel ────────────────────────────────────
    def export_xlsx(self, bom_id, include_price=False, price_date=None, batch_id=None):
        """把一份 BOM 的完整多层结构导出成 Excel（与页面上的树一致：序号按层级编号）。

        返回 (bytes, 文件名)；BOM 不存在返回 (None, 错误信息)。
        """
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from services.common.excel_text import safe_excel_text as t   # 防公式注入（Codex 审计 #6）

        res = self.tree(bom_id, include_price=include_price, price_date=price_date, batch_id=batch_id)
        if not res.success:
            return None, res.message
        bom, children = res.data['bom'], res.data['children']

        wb = Workbook()
        ws = wb.active
        ws.title = 'BOM'
        headers = ['序号', '层级', '图纸编码', 'ERP编码', '名称', '数量', '单位']
        if include_price:
            headers += ['单价', '金额', '价格日期']
        ws.append([t(f"BOM：{bom['drawing']}  {bom.get('name') or ''}")])
        ws.append([f"ERP编码：{bom.get('erp_code') or '未匹配'}    导入：{bom.get('imported_by') or '—'} "
                   f"{bom.get('imported_at') or ''}    导出：{now_cst().strftime('%Y-%m-%d %H:%M')}"
                   + (f"    计价：{bom.get('priced_as_of') or '最新价格'}    合计单价："
                      f"{bom['unit_price'] if bom.get('unit_price') is not None else '未计价'}"
                      + (f"（{bom['missing']} 项无价格）" if bom.get('missing') else '')
                      if include_price else '')])
        ws.append([])
        ws.append(headers)
        ws['A1'].font = Font(bold=True, size=13)
        ws['A2'].font = Font(size=10, color='6B5E4E')
        head_fill = PatternFill('solid', fgColor='F5F0E8')
        thin = Side(style='thin', color='E0D4C0')
        for cell in ws[4]:
            cell.font = Font(bold=True)
            cell.fill = head_fill
            cell.border = Border(bottom=thin)

        def walk(nodes, prefix, depth):
            for i, n in enumerate(nodes, start=1):
                seq = f'{prefix}.{i}' if prefix else str(i)
                row_values = [seq, depth, t(n['drawing']), t(n.get('erp_code') or ''), t(n.get('name') or ''),
                              n.get('qty'), t(n.get('unit') or '')]
                if include_price:
                    row_values += [n.get('unit_price'), n.get('amount'), n.get('price_date') or '']
                ws.append(row_values)
                row = ws.max_row
                # 编码按层级缩进，打开就能看出结构
                ws.cell(row, 3).alignment = Alignment(indent=depth - 1)
                if depth == 1:
                    ws.cell(row, 1).font = Font(bold=True)
                    ws.cell(row, 3).font = Font(bold=True)
                if n.get('children'):
                    walk(n['children'], seq, depth + 1)

        walk(children, '', 1)
        for col, width in zip('ABCDEFGHIJ', (12, 6, 22, 20, 60, 10, 8, 12, 12, 12)):
            ws.column_dimensions[col].width = width
        ws.freeze_panes = 'A5'

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue(), f"BOM-{bom['drawing']}.xlsx"

    # ── 物料视角：自身 BOM + 被哪些产品使用 ─────────────
    def for_material(self, erp_code):
        """物料卡片用：该 ERP 物料挂的全部研发 BOM（每个研发版本一条，带下级数量）+
        反查使用它的上级与最终产品。下级结构不在这里展开，卡片点「查看」时单独调 tree()。"""
        versions = (MaterialBom.query.filter(MaterialBom.erp_code == erp_code)
                    .order_by(MaterialBom.version.desc()).all())
        line_counts = dict(
            db.session.query(MaterialBomLine.bom_id, func.count(MaterialBomLine.id))
            .filter(MaterialBomLine.bom_id.in_([b.id for b in versions]))
            .group_by(MaterialBomLine.bom_id).all()
        ) if versions else {}

        # 直接上级：子件行里对应到本物料的
        direct_lines = MaterialBomLine.query.filter(MaterialBomLine.erp_code == erp_code).all()
        parent_ids = {l.bom_id for l in direct_lines}
        parents = {b.id: b for b in MaterialBom.query.filter(MaterialBom.id.in_(parent_ids)).all()} \
            if parent_ids else {}
        direct = []
        for l in direct_lines:
            p = parents.get(l.bom_id)
            if p:
                direct.append({**p.to_dict(), 'qty': l.qty, 'unit': l.unit,
                               'child_drawing': _drawing(l.code, l.version)})
        direct.sort(key=lambda x: (x['code'], x['version']))

        # 最终产品：沿上级一路往上找，直到不再被任何 BOM 引用的顶层父件；每层一次查询
        tops = {}
        seen = set()
        frontier = list(parents.values())
        for _ in range(_MAX_DEPTH):
            frontier = [b for b in frontier if (b.code, b.version) not in seen]
            if not frontier:
                break
            seen.update((b.code, b.version) for b in frontier)
            keys = [(b.code, b.version) for b in frontier]
            uses = MaterialBomLine.query.filter(
                tuple_(MaterialBomLine.code, MaterialBomLine.version).in_(keys)
            ).all()
            used = {(l.code, l.version) for l in uses}
            for b in frontier:
                if (b.code, b.version) not in used:
                    tops[b.id] = b
            up_ids = {l.bom_id for l in uses}
            frontier = MaterialBom.query.filter(MaterialBom.id.in_(up_ids)).all() if up_ids else []

        top_list = sorted((b.to_dict() for b in tops.values()),
                          key=lambda x: (x['code'], x['version']))
        # 研发版本 / 上级 / 最终产品的名称都优先用 ERP 的（一次查询）
        version_list = [{**b.to_dict(), 'line_count': line_counts.get(b.id, 0)} for b in versions]
        _apply_erp_names(version_list + direct + top_list)
        return Result.ok(data={
            'versions': version_list,
            'direct_parents': direct,
            'top_products': top_list,
        })

    @staticmethod
    def codes_with_bom(erp_codes):
        """物料表当前页里哪些物料有 BOM（一条查询）。"""
        if not erp_codes:
            return set()
        return {
            c for (c,) in db.session.query(MaterialBom.erp_code)
            .filter(MaterialBom.erp_code.in_(list(erp_codes))).distinct().all()
        }


material_bom_service = MaterialBomService()
