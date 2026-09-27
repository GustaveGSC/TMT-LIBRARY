"""物料 BOM（研发 BOM）：导入、展开查看、反查被哪些产品使用。

只收研发 BOM（采购 BOM 只作价格来源，不在这里）。Excel 是多层展开的层次表，
支持 PDM 导出（物料编码+版本）与 ERP 导出（图号）两种格式，表头识别复用变更申请单的
`_bom_columns`。导入时把树拆成「每个有下级的节点一份单层 BOM」存储，查看时逐层展开。

编码对应：研发版本比 ERP 细——成品/产成品 ERP 编码只到 -A，研发是 -A01/-A02；
半成品/原材料 ERP 编码本身就带 -A01。所以按「完整版本 → 仅字母版本 → 无版本」顺序
去 ERP 物料表里找对应编码。
"""
import io
import re

from openpyxl import load_workbook
from sqlalchemy import func, or_, tuple_

from database.base import db
from database.models.product.import_raw import ImportProductRaw
from database.models.product.material import MaterialBom, MaterialBomLine
from result import Result
from services.rd.change_documents import (
    _bom_columns, _category_name, _level_str, _numeric_code_text,
)
from upload_validation import UploadValidationError, ensure_spreadsheet_row_limit
from utils import now_cst


_VERSION_LETTERS_RE = re.compile(r'^([A-Za-z]+)\d+$')
# 展开/反查的最大层数，防止数据里出现环（A 含 B、B 又含 A）时死循环
_MAX_DEPTH = 20


def _drawing(code, version):
    return f'{code}-{version}' if version else code


def parse_bom_rows(data: bytes):
    """解析研发 BOM Excel，按文件顺序返回行：level/code/version/name/spec/category/qty/unit。"""
    wb = load_workbook(io.BytesIO(data), data_only=True, read_only=False)
    try:
        ws = wb.active
        format_name, col_map = _bom_columns(ws)

        def get(r, name):
            c = col_map.get(name)
            return ws.cell(r, c).value if c else None

        rows = []
        for r in range(2, ws.max_row + 1):
            ensure_spreadsheet_row_limit(r)
            level = _level_str(get(r, '层次'))
            if not level:
                continue
            if format_name == 'erp':
                drawing = str(get(r, '图号') or '').strip()
                if not drawing:
                    continue
                idx = drawing.rfind('-')
                code = drawing[:idx] if idx > 0 else drawing
                version = drawing[idx + 1:] if idx > 0 else ''
                name = str(get(r, '品名') or '').strip()
                spec = str(get(r, '规格') or '').strip()
                category = None
            else:
                code = _numeric_code_text(ws.cell(r, col_map['物料编码']))
                if not code:
                    continue
                version = str(get(r, '版本') or '').strip()
                category = _category_name(get(r, '一级分类')) or None
                names = [
                    _category_name(get(r, col))
                    for col in ('二级分类', '三级分类')
                    if _category_name(get(r, col))
                ]
                description = str(get(r, '描述') or '').strip()
                name = description or '_'.join(names)
                spec = str(get(r, '规格') or '').strip()
            try:
                qty = float(get(r, '数量'))
            except (TypeError, ValueError):
                qty = 1.0
            rows.append({
                'level': level, 'code': code, 'version': version,
                'name': name or None, 'spec': spec or None, 'category': category,
                'qty': qty, 'unit': str(get(r, '单位') or '').strip() or None,
            })
        return rows
    finally:
        wb.close()


def build_single_level_boms(rows):
    """把层次行拆成单层 BOM：{(code, version): {'head': row, 'lines': [row+qty]}}。

    同一父件在文件里被展开多次（同一半成品挂在多个上级下）时内容相同，只取第一次；
    同一父件下同一子件出现多行时合并数量。
    """
    by_level = {}
    boms = {}
    for row in rows:
        by_level[row['level']] = row
        dot = row['level'].rfind('.')
        if dot < 0:
            continue
        parent = by_level.get(row['level'][:dot])
        if parent is None:
            continue
        key = (parent['code'], parent['version'])
        entry = boms.setdefault(key, {'head': parent, 'lines': {}, 'owner': parent['level']})
        # 只采用该父件第一次出现时的展开，后面重复展开的整段跳过
        if entry['owner'] != parent['level']:
            continue
        child_key = (row['code'], row['version'])
        line = entry['lines'].get(child_key)
        if line:
            line['qty'] += row['qty']
        else:
            entry['lines'][child_key] = dict(row)
    return {
        key: {'head': v['head'], 'lines': list(v['lines'].values())}
        for key, v in boms.items()
    }


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


class MaterialBomService:

    # ── 编码对应 ──────────────────────────────────────
    @staticmethod
    def _erp_resolver(pairs):
        """返回 (code, version) → ERP 编码 的函数；只查一次库。"""
        candidates = set()
        for code, version in pairs:
            candidates.add(code)
            if version:
                candidates.add(f'{code}-{version}')
                m = _VERSION_LETTERS_RE.match(version)
                if m:
                    candidates.add(f'{code}-{m.group(1)}')
        existing = set()
        cand = list(candidates)
        for i in range(0, len(cand), 1000):
            existing.update(
                c for (c,) in db.session.query(ImportProductRaw.code)
                .filter(ImportProductRaw.code.in_(cand[i:i + 1000])).all()
            )

        def resolve(code, version):
            if version:
                if f'{code}-{version}' in existing:
                    return f'{code}-{version}'
                m = _VERSION_LETTERS_RE.match(version)
                if m and f'{code}-{m.group(1)}' in existing:
                    return f'{code}-{m.group(1)}'
            return code if code in existing else None
        return resolve

    # ── 导入 ──────────────────────────────────────────
    def import_file(self, data: bytes, filename: str, username: str):
        try:
            rows = parse_bom_rows(data)
        except UploadValidationError as exc:
            return Result.fail(str(exc))
        if not rows:
            return Result.fail('文件中没有有效的 BOM 行')
        boms = build_single_level_boms(rows)
        if not boms:
            return Result.fail('文件中没有带下级的物料，无法生成 BOM')

        pairs = {(r['code'], r['version']) for r in rows}
        resolve = self._erp_resolver(pairs)
        existing = {
            (b.code, b.version): b for b in MaterialBom.query.filter(
                tuple_(MaterialBom.code, MaterialBom.version).in_(list(boms.keys()))
            ).all()
        } if boms else {}

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

        unmatched = sorted({
            _drawing(c, v) for c, v in pairs if resolve(c, v) is None
        })
        roots = [r for r in rows if '.' not in r['level']]
        return Result.ok(data={
            'created': created, 'updated': updated, 'lines': line_count,
            'roots': [_drawing(r['code'], r['version']) for r in roots],
            'unmatched': unmatched,
        })

    # ── 列表 ──────────────────────────────────────────
    def list_boms(self, keyword=None, category=None, page=1, page_size=50):
        q = MaterialBom.query
        if keyword:
            like = f'%{keyword}%'
            q = q.filter(or_(
                MaterialBom.code.like(like), MaterialBom.erp_code.like(like),
                MaterialBom.name.like(like), MaterialBom.spec.like(like),
            ))
        if category:
            q = q.filter(MaterialBom.category == category)
        total = q.count()
        rows = (q.order_by(MaterialBom.code.asc(), MaterialBom.version.desc())
                .offset((page - 1) * page_size).limit(page_size).all())
        counts = dict(
            db.session.query(MaterialBomLine.bom_id, func.count(MaterialBomLine.id))
            .filter(MaterialBomLine.bom_id.in_([r.id for r in rows]))
            .group_by(MaterialBomLine.bom_id).all()
        ) if rows else {}
        categories = [c for (c,) in db.session.query(MaterialBom.category).distinct().all() if c]
        return Result.ok(data={
            'items': [{**r.to_dict(), 'line_count': counts.get(r.id, 0)} for r in rows],
            'total': total, 'page': page, 'page_size': page_size,
            'categories': sorted(categories),
        })

    def delete_bom(self, bom_id):
        bom = db.session.get(MaterialBom, bom_id)
        if bom is None:
            return Result.fail('BOM 不存在')
        MaterialBomLine.query.filter_by(bom_id=bom_id).delete(synchronize_session=False)
        db.session.delete(bom)
        db.session.commit()
        return Result.ok()

    # ── 展开 ──────────────────────────────────────────
    def tree(self, bom_id):
        """展开一份 BOM 的完整多层结构；每层一次查询（O(层数)）。"""
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

        def build(bom, path, depth):
            nodes = []
            for line in lines_by_bom.get(bom.id, []):
                key = (line.code, line.version)
                child_bom = boms_by_key.get(key)
                erp_name, erp_spec = info.get(line.erp_code, (None, None))
                node = {
                    'id': f'{bom.id}-{line.id}',
                    'code': line.code, 'version': line.version,
                    'drawing': _drawing(line.code, line.version),
                    'erp_code': line.erp_code,
                    'name': erp_name or line.name, 'spec': erp_spec or line.spec,
                    'category': line.category, 'qty': line.qty, 'unit': line.unit,
                    'bom_id': child_bom.id if child_bom else None,
                }
                if child_bom and key not in path and depth < _MAX_DEPTH:
                    node['children'] = build(child_bom, path | {key}, depth + 1)
                nodes.append(node)
            return nodes

        root_dict = root.to_dict()
        root_name, root_spec = info.get(root.erp_code, (None, None))
        root_dict['name'] = root_name or root.name
        root_dict['spec'] = root_spec or root.spec
        return Result.ok(data={
            'bom': root_dict,
            'children': build(root, {(root.code, root.version)}, 1),
        })

    # ── 物料视角：自身 BOM + 被哪些产品使用 ─────────────
    def for_material(self, erp_code, bom_id=None):
        """物料卡片用：该 ERP 物料的研发 BOM（可能有多个研发版本）+ 反查使用它的上级与最终产品。"""
        versions = (MaterialBom.query.filter(MaterialBom.erp_code == erp_code)
                    .order_by(MaterialBom.version.desc()).all())
        selected = None
        if versions:
            selected = next((b for b in versions if b.id == bom_id), versions[0])
        tree = self.tree(selected.id).data['children'] if selected else []

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
        # 上级/最终产品的名称同样优先用 ERP 的
        info = _erp_info([d['erp_code'] for d in direct + top_list])
        for d in direct + top_list:
            erp_name, erp_spec = info.get(d['erp_code'], (None, None))
            d['name'] = erp_name or d['name']
            d['spec'] = erp_spec or d['spec']
        return Result.ok(data={
            'versions': [b.to_dict() for b in versions],
            'selected_id': selected.id if selected else None,
            'tree': tree,
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
