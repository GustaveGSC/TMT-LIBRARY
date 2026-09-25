"""ECR、ECN 与 BOM 文件的纯解析、比对和工作簿生成逻辑。"""

import io
import os
import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from error_handling import report_internal_error
from upload_validation import UploadValidationError

_THIN  = Side(style='thin')
_THICK = Side(style='medium')

def _border(left=True, right=True, top=True, bottom=True, thick=False):
    s = _THICK if thick else _THIN
    return Border(
        left=s   if left   else Side(),
        right=s  if right  else Side(),
        top=s    if top    else Side(),
        bottom=s if bottom else Side(),
    )

def _font(name='宋体', size=10, bold=False, color='000000'):
    return Font(name=name, size=size, bold=bold, color=color)

def _align(horiz='left', vert='center', wrap=False):
    return Alignment(horizontal=horiz, vertical=vert, wrap_text=wrap)

def _fill(hex_color):
    return PatternFill(fill_type='solid', fgColor=hex_color)

FILL_HEADER = _fill('F0EDE6')
FILL_WHITE  = _fill('FFFFFF')
FILL_CANCEL = _fill('FDECEA')   # 取消行：浅红
BORDER_ALL  = _border()

STATUS_PUBLISHED = '已发布'
STATUS_DISABLED = '已停用'
STATUS_NEW = '审核中'
STATUS_COMMON_CHANGE = '通用变更审核中'
STATUS_NON_COMMON_CHANGE = '非通用变更审核中'
CHANGE_STATUSES = {STATUS_COMMON_CHANGE, STATUS_NON_COMMON_CHANGE}
# “已停用”是已发布物料仍保留在 BOM 中的另一种写法，不代表本次变更。
PUBLISHED_STATUSES = {STATUS_PUBLISHED, STATUS_DISABLED}
VALID_BOM_STATUSES = PUBLISHED_STATUSES | {
    STATUS_NEW, STATUS_COMMON_CHANGE, STATUS_NON_COMMON_CHANGE,
}


def _set(ws, row, col, value, font=None, align=None, border=None, fill=None):
    cell = ws.cell(row=row, column=col, value=value)
    if font:   cell.font      = font
    if align:  cell.alignment = align
    if border: cell.border    = border
    if fill:   cell.fill      = fill
    return cell


def _merge(ws, r1, c1, r2, c2, value, font=None, align=None, fill=None):
    ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)
    top_left = ws.cell(row=r1, column=c1, value=value)
    if font:  top_left.font      = font
    if align: top_left.alignment = align
    if fill:  top_left.fill      = fill
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            ws.cell(row=r, column=c).border = BORDER_ALL
    return top_left


# ── checkbox 文本 ──────────────────────────────────────

def _auto_col_widths(ws, min_w=5, max_w=50):
    """根据单元格内容自动调整列宽（CJK 字符计 2，ASCII 计 1）。
    合并单元格按列数均分宽度，多行内容取最长行。"""
    # 找出所有合并区域的顶左格 → 列 span；及非顶左格（跳过）
    merge_spans = {}
    merged_secondary = set()
    for mc in ws.merged_cells.ranges:
        merge_spans[(mc.min_row, mc.min_col)] = mc.max_col - mc.min_col + 1
        for r in range(mc.min_row, mc.max_row + 1):
            for c in range(mc.min_col, mc.max_col + 1):
                if r != mc.min_row or c != mc.min_col:
                    merged_secondary.add((r, c))

    col_max = {}
    for row in ws.iter_rows():
        for cell in row:
            if (cell.row, cell.column) in merged_secondary or cell.value is None:
                continue
            text = str(cell.value)
            # 取多行中最长一行的宽度
            line_w = max(
                sum(2 if ord(ch) > 0x2E7F else 1 for ch in line)
                for line in text.split('\n')
            ) + 2  # +2 留白
            # 合并单元格按列数均分
            span = merge_spans.get((cell.row, cell.column), 1)
            per_col = line_w / span if span > 1 else line_w
            col = cell.column
            if per_col > col_max.get(col, 0):
                col_max[col] = per_col

    for col in range(1, ws.max_column + 1):
        w = col_max.get(col, min_w)
        ws.column_dimensions[get_column_letter(col)].width = max(min(round(w), max_w), min_w)


def _mark(options, selected, other_text=''):
    """生成 ☑/☐ 选择文本；other_text 为"其他"被选中时的自定义说明（显示为 其他：XXX）"""
    parts = []
    for opt in options:
        checked = opt in (selected if isinstance(selected, list) else [selected])
        if checked and opt == '其他' and other_text:
            parts.append(f'☑ 其他：{other_text}')
        else:
            parts.append(f'{"☑" if checked else "☐"} {opt}')
    return '    '.join(parts)


# ── BOM 比对 ──────────────────────────────────────────

def _level_str(v):
    """将层次单元格值统一转为字符串"""
    if v is None:
        return ''
    if isinstance(v, float):
        return str(int(v)) if v == int(v) else str(v)
    if isinstance(v, int):
        return str(v)
    return str(v).strip()


def _level_sort_key(level_str):
    """将 '1.1.2' 转为可排序元组 (1, 1, 2)"""
    try:
        return tuple(int(x) for x in level_str.split('.') if x)
    except ValueError:
        return (0,)


_ERP_BOM_REQUIRED_COLS = ['层次', '图号', '品名', '规格', '数量', '单位', '状态']
_PDM_BOM_REQUIRED_COLS = [
    '层次', '物料编码', '版本', '一级分类', '二级分类', '描述', '数量', '单位', '状态',
]


def _bom_columns(ws):
    """返回 (格式, 首个同名表头映射)，必需表头重复时明确拒绝。"""
    occurrences = {}
    for column in range(1, ws.max_column + 1):
        value = ws.cell(1, column).value
        if value is None or not str(value).strip():
            continue
        occurrences.setdefault(str(value).strip(), []).append(column)

    names = set(occurrences)
    if '图号' in names:
        format_name = 'erp'
        required = _ERP_BOM_REQUIRED_COLS
    elif {'物料编码', '一级分类'} <= names:
        format_name = 'pdm'
        required = _PDM_BOM_REQUIRED_COLS
    else:
        raise UploadValidationError('无法识别的 BOM 文件格式')

    duplicates = [name for name in required if len(occurrences.get(name, [])) > 1]
    if duplicates:
        name = duplicates[0]
        columns = '、'.join(str(column) for column in occurrences[name])
        raise UploadValidationError(
            f'表头中「{name}」出现了 {len(occurrences[name])} 次（第 {columns} 列），请确认导出模板'
        )
    missing = [name for name in required if name not in occurrences]
    if missing:
        raise UploadValidationError('缺少必要列：' + ', '.join(missing))
    return format_name, {name: columns[0] for name, columns in occurrences.items()}


def _numeric_code_text(cell):
    """读取混合类型编码；纯 0 数字格式用于恢复 Excel 展示中的前导零。"""
    value = cell.value
    if value is None:
        return ''
    if isinstance(value, bool):
        raise UploadValidationError(f'第 {cell.row} 行物料编码不是有效文本')
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        # PDM 偶尔会把带点的子件编码存成数值。这类编码会在后续按既有
        # 规则跳过，不应为了一个不参与 BOM 比对的值阻断整份文件。
        text = str(int(value)) if value.is_integer() else repr(value)
    else:
        return str(value).strip()
    number_format = str(cell.number_format or '').strip()
    if '.' not in text and number_format and set(number_format) == {'0'}:
        text = text.zfill(len(number_format))
    return text


def _category_name(value):
    text = str(value or '').strip()
    return text.split('_', 1)[1] if '_' in text else text


def _pdm_spec(get_value, version, is_packaged):
    effective_version = version or 'A01'
    if is_packaged:
        series_version = str(get_value('系列版本') or '').strip()
        prefix = f'({series_version})' if series_version else ''
        body = ''.join(str(get_value(name) or '').strip() for name in (
            '备注', '类别', '尺寸', '材料', '颜色',
        ))
        return f'{prefix}{body}_{effective_version}'
    third = next((
        str(get_value(name) or '').strip()
        for name in ('表面处理', '备注', '颜色')
        if str(get_value(name) or '').strip()
    ), '')
    return '_'.join([
        str(get_value('适配产品') or '').strip(),
        str(get_value('规格') or '').strip(),
        third,
        effective_version,
    ])

def validate_bom(path, role='before'):
    """校验 BOM 文件合法性，返回错误消息字符串；无误返回 None。
    role='any'   ：只校验列名，不校验状态
    role='before'：变更前文件，要求状态列全部为发布态（已废弃，保留供兼容）
    role='after' ：变更审核中文件，要求状态列不能全是发布态
    """
    from openpyxl import load_workbook
    try:
        wb = load_workbook(path, data_only=True, read_only=True)
    except Exception:
        label = '变更前文件' if role == 'before' else '变更审核中文件'
        error_id = report_internal_error(f'{label}读取失败')
        return f'{label}无法读取（错误编号：{error_id}）'
    ws = wb.active

    label = '变更前文件' if role == 'before' else '变更审核中文件'
    try:
        _format_name, col_map = _bom_columns(ws)
    except UploadValidationError as exc:
        wb.close()
        return f'{label}{exc}'

    # 2. 状态列校验（跳过空行）
    status_col = col_map['状态']
    statuses = []
    for r in range(2, ws.max_row + 1):
        v = ws.cell(r, status_col).value
        if v is not None and str(v).strip():
            statuses.append(str(v).strip())
    wb.close()

    if not statuses:
        return f'{label}中未找到任何有效数据行'

    unknown = sorted(set(statuses) - VALID_BOM_STATUSES)
    if unknown:
        return f'{label}包含未知状态：{"、".join(unknown)}'

    if role == 'after':
        if all(s in PUBLISHED_STATUSES for s in statuses):
            return (
                '变更审核中文件的状态列全部为「已发布」（含「已停用」），'
                '该文件应包含处于审核中状态的物料'
            )

    return None


def _parse_bom(path):
    """读取并清洗 BOM 文件，返回 {(父级编码, 编码): item} 字典。

    key 使用 (parent_code, code) 而非 (level, code)，使得同一父级下零件
    顺序调整时不会被误判为删除+新增。
    """
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True)
    ws = wb.active

    format_name, col_map = _bom_columns(ws)

    def _get(row, name, default=''):
        c = col_map.get(name)
        return ws.cell(row, c).value if c else default

    # 与 validate_bom 一致，一次报告文件里的全部未知状态，避免逐项修正。
    statuses = {
        str(_get(r, '状态') or '').strip()
        for r in range(2, ws.max_row + 1)
        if str(_get(r, '状态') or '').strip()
    }
    unknown = sorted(statuses - VALID_BOM_STATUSES)
    if unknown:
        wb.close()
        raise UploadValidationError(f'包含未知状态：{"、".join(unknown)}')

    # 第一遍：按行顺序收集所有有效行（保留 level 供第二遍查父级）
    rows = []
    for r in range(2, ws.max_row + 1):
        level = _level_str(_get(r, '层次'))
        status = str(_get(r, '状态') or '').strip()
        if not level:
            continue
        if format_name == 'erp':
            drawing = str(_get(r, '图号') or '').strip()
            if not drawing:
                continue
            idx = drawing.rfind('-')
            code = drawing[:idx] if idx > 0 else drawing
            version = drawing[idx + 1:] if idx > 0 else ''
            name = str(_get(r, '品名') or '').strip()
            spec = _complete_spec_version(str(_get(r, '规格') or '').strip(), version)
        else:
            code = _numeric_code_text(ws.cell(r, col_map['物料编码']))
            version = str(_get(r, '版本') or '').strip()
            if not code:
                continue
            if not version and status != STATUS_NEW:
                continue
            drawing = f'{code}-{version}' if version else ''
            categories = [
                _category_name(_get(r, column))
                for column in ('一级分类', '二级分类', '三级分类')
                if _category_name(_get(r, column))
            ]
            description = str(_get(r, '描述') or '').strip()
            name = '_'.join([*categories, description] if description else categories)
            spec = _pdm_spec(
                lambda column: _get(r, column), version,
                bool(categories and categories[0] == '产成品'),
            )

        if not code:
            continue

        if '.' in code or code.startswith('14ST10'):
            continue

        qty_raw = _get(r, '数量', 1)
        try:
            qty = float(qty_raw)
        except (TypeError, ValueError):
            qty = 1.0

        rows.append({
            'level':   level,
            'code':    code,
            'version': version,
            'drawing': drawing,
            'name':    name,
            'spec':    spec,
            'qty':     qty,
            'unit':    str(_get(r, '单位') or 'PCS').strip(),
            'status':  status,
        })

    # 第二遍：建立 level → code 映射，用于查找父级编码
    level_to_code = {row['level']: row['code'] for row in rows}

    items = {}
    for row in rows:
        level = row['level']
        dot_idx = level.rfind('.')
        parent_level = level[:dot_idx] if dot_idx >= 0 else ''
        parent_code  = level_to_code.get(parent_level, '')
        key = (parent_code, row['code'])
        items[key] = row

    wb.close()
    return items


def _qty_str(qty):
    return str(int(qty)) if qty == int(qty) else str(qty)


# ── 版本号推算 ──────────────────────────────────────────

_VERSION_RE = re.compile(r'^([A-Za-z]+)(\d+)$')

def _complete_spec_version(spec, version):
    """规格版本补全：若图号版本为 'D01'，而规格中含 '_D'（只有字母、缺数字），
    自动补全为 '_D01'。避免误替换后面已有数字的情况。"""
    if not spec or not version:
        return spec
    m = _VERSION_RE.match(version.strip())
    if not m:
        return spec
    letters = m.group(1)
    num     = m.group(2)
    # 匹配 _{letters}（不区分大小写），且后面不跟数字
    pattern = re.compile(r'(_' + re.escape(letters) + r')(?!\d)', re.IGNORECASE)
    return pattern.sub(lambda x: x.group(1) + num, spec)


def _next_version(version, is_non_common):
    """推算变更后版本号
    - 通用变更审核中（is_non_common=False）：数字+1，字母不变。A01→A02，B02→B03
    - 非通用变更审核中（is_non_common=True）：最后一个字母+1，数字重置01。A01→B01，B02→C01
    """
    m = _VERSION_RE.match(version.strip())
    if not m:
        return version  # 无法解析，保持原样
    letters   = m.group(1).upper()
    number    = int(m.group(2))
    num_width = len(m.group(2))  # 保持数字位宽（如 01 → 宽度 2）
    if is_non_common:
        new_letters = letters[:-1] + chr(ord(letters[-1]) + 1)
        new_number  = 1
    else:
        new_letters = letters
        new_number  = number + 1
    return f"{new_letters}{str(new_number).zfill(num_width)}"


def _derive_new_drawing(item):
    """根据 item 的状态推算新图号；若非审核中则返回原图号"""
    status = item.get('status', '')
    if status == STATUS_NEW:
        return f"{item['code']}-A01"
    if status not in CHANGE_STATUSES:
        return item['drawing']
    is_non_common = status == STATUS_NON_COMMON_CHANGE
    new_ver = _next_version(item['version'], is_non_common)
    return f"{item['code']}-{new_ver}"


def _update_spec_version(spec, old_ver, new_ver):
    """将规格字符串中旧版本号替换为新版本号（处理 -版本 和 _版本 两种前缀格式）"""
    if not spec or not old_ver or not new_ver or old_ver == new_ver:
        return spec
    result = spec.replace(f'-{old_ver}', f'-{new_ver}')
    result = result.replace(f'_{old_ver}', f'_{new_ver}')
    return result


def compare_bom(before_path, after_path):
    """比对两个 BOM，返回 {changes, stats}

    规则：
    - 状态为"审核中"的物料 → 生成取消行（旧版本）+ 新增行（推算后的新版本）
    - 纯新增物料 → 生成一行新增（若为审核中则图号推算为新版本）
    - 仅在 before 存在的物料 → 生成一行取消
    - 排序按层次深度优先（1 < 1.1 < 1.1.1 < 1.2 < 2 ...）
    """
    before = _parse_bom(before_path)
    after  = _parse_bom(after_path)

    # 层次 → item 映射（层次在同一份 BOM 中唯一），用于查找父级
    before_by_level = {item['level']: item for item in before.values()}
    after_by_level  = {item['level']: item for item in after.values()}

    def _parent_item(level, by_level):
        """返回父级 item 或 None"""
        idx = level.rfind('.')
        if idx < 0:
            return None
        return by_level.get(level[:idx])

    def _old_main_drawing(level):
        """取消行/deleted行的主件图号：after BOM 中父级的当前图号（旧版本）"""
        p = _parent_item(level, after_by_level)
        return p['drawing'] if p else ''

    def _new_main_drawing(level):
        """新增行/added行的主件图号：after BOM 中父级的推算新图号（若父级也在变更）"""
        p = _parent_item(level, after_by_level)
        return _derive_new_drawing(p) if p else ''

    def _before_main_drawing(level):
        """deleted 行主件图号：before BOM 中父级的图号"""
        p = _parent_item(level, before_by_level)
        return p['drawing'] if p else ''

    # 按层次排序（深度优先）；key 已改为 (parent_code, code)，用 item['level'] 排序
    def _key_level(k):
        item = before.get(k) or after.get(k)
        return _level_sort_key(item['level']) if item else (0,)

    all_keys = sorted(set(before) | set(after), key=_key_level)

    changes   = []
    n_version = 0   # 版本变更物料对数
    n_added   = 0
    n_deleted = 0

    for key in all_keys:
        in_b, in_a = key in before, key in after

        if in_b and in_a:
            # 在两个 BOM 中都存在：检查是否为审核中（即将变更）
            a = after[key]
            b = before[key]
            is_ecr = a['status'] in CHANGE_STATUSES
            qty_changed = abs(b['qty'] - a['qty']) > 1e-9

            if not (is_ecr or qty_changed):
                continue  # 无变化，跳过

            n_version += 1

            if is_ecr:
                # 版本变更（含通用/非通用）：生成取消+新增两行
                is_non_common = a['status'] == STATUS_NON_COMMON_CHANGE
                kind = '非通用变更' if is_non_common else '通用变更'

                old_drawing = a['drawing']
                old_version = a['version']
                new_version = _next_version(old_version, is_non_common)
                new_drawing = f"{a['code']}-{new_version}"
                new_spec    = _update_spec_version(a['spec'], old_version, new_version)

                # 取消行：取消旧版本，主件图号为 after 父级当前图号
                changes.append({
                    'row_type':      'cancel',
                    'change_kind':   kind,
                    'level':         a['level'],
                    'main_drawing':  _old_main_drawing(a['level']),
                    'drawing':       old_drawing,
                    'name':          a['name'],
                    'spec':          a['spec'],
                    'qty':           b['qty'],
                    'change_method': '取消',
                    '_code':         a['code'],
                    '_parent_code':  key[0],
                })
                # 新增行：新增新版本，主件图号为 after 父级推算后的新图号
                changes.append({
                    'row_type':      'add',
                    'change_kind':   kind,
                    'level':         a['level'],
                    'main_drawing':  _new_main_drawing(a['level']),
                    'drawing':       new_drawing,
                    'name':          a['name'],
                    'spec':          new_spec,
                    'qty':           a['qty'],
                    'change_method': '新增',
                    '_code':         a['code'],
                    '_parent_code':  key[0],
                })
            else:
                # 纯数量变更：只生成单行，变更方式为"数量变更"，取替代关系显示数量变化
                qty_desc = f"{_qty_str(b['qty'])}→{_qty_str(a['qty'])} {a['unit']}"
                changes.append({
                    'row_type':      'added',
                    'change_kind':   '数量变更',
                    'qty_desc':      qty_desc,
                    'level':         a['level'],
                    'main_drawing':  _new_main_drawing(a['level']),
                    'drawing':       a['drawing'],
                    'name':          a['name'],
                    'spec':          a['spec'],
                    'qty':           a['qty'],
                    'change_method': '数量变更',
                    '_code':         a['code'],
                    '_parent_code':  key[0],
                })

        elif in_b:
            # 仅在 before 中存在（已删除）
            b = before[key]
            n_deleted += 1
            changes.append({
                'row_type':      'deleted',
                'change_kind':   '删除',
                'level':         b['level'],
                'main_drawing':  _before_main_drawing(b['level']),
                'drawing':       b['drawing'],
                'name':          b['name'],
                'spec':          b['spec'],
                'qty':           b['qty'],
                'change_method': '取消',
                '_code':         b['code'],
                '_parent_code':  key[0],
            })

        else:
            # 仅在 after 中存在（新增）
            a = after[key]
            n_added += 1
            is_brand_new  = a['status'] == STATUS_NEW
            is_ecr_new    = a['status'] in CHANGE_STATUSES
            is_non_common = a['status'] == STATUS_NON_COMMON_CHANGE
            old_version   = a['version']
            if is_brand_new:
                new_version = 'A01'
                new_drawing = f"{a['code']}-A01"
                new_spec = a['spec']
            else:
                new_version = _next_version(old_version, is_non_common) if is_ecr_new else old_version
                new_drawing = f"{a['code']}-{new_version}" if is_ecr_new else a['drawing']
                new_spec = _update_spec_version(a['spec'], old_version, new_version)
            changes.append({
                'row_type':      'added',
                'change_kind':   '新增',
                'level':         a['level'],
                'main_drawing':  _new_main_drawing(a['level']),
                'drawing':       new_drawing,
                'name':          a['name'],
                'spec':          new_spec,
                'qty':           a['qty'],
                'change_method': '新增',
                '_code':         a['code'],
                '_parent_code':  key[0],
            })

    # ── 后处理：去除因子装配替换产生的子零件假增删 ──────────────
    # 当一个子装配整体被替换（旧装配被删、新装配被新增），其共有的子零件
    # 会因 parent_code 不同而产生一组 deleted+added 噪声。过滤规则：
    #   deleted 行：父级编码本身也在 deleted 集合中，且该零件编码也出现在 added 集合里 → 噪声
    #   added  行：父级编码本身也在 added  集合中，且该零件编码也出现在 deleted 集合里 → 噪声
    deleted_codes = {ch['_code'] for ch in changes if ch['row_type'] == 'deleted'}
    added_codes   = {ch['_code'] for ch in changes if ch['row_type'] == 'added'}

    filtered = []
    for ch in changes:
        if ch['row_type'] == 'deleted':
            if ch['_parent_code'] in deleted_codes and ch['_code'] in added_codes:
                n_deleted -= 1
                continue  # 噪声：父装配也被删除，且同编码已在新装配中新增
        elif ch['row_type'] == 'added':
            if ch['_parent_code'] in added_codes and ch['_code'] in deleted_codes:
                n_added -= 1
                continue  # 噪声：父装配也是新增，且同编码已从旧装配中删除
        filtered.append(ch)
    changes = filtered

    for i, ch in enumerate(changes):
        ch['seq'] = i + 1
        # 清理内部字段，不返回给前端
        ch.pop('_code', None)
        ch.pop('_parent_code', None)

    stats = {
        'version': n_version,
        'added':   n_added,
        'deleted': n_deleted,
        'total':   len(changes),
    }
    after_codes = sorted({item['code'] for item in after.values()})
    return {'changes': changes, 'stats': stats, 'after_codes': after_codes}


# ── ECN 选项常量 ──────────────────────────────────────

_IMPORT_OPTS         = ['立即导入', '清化库存', '随单导入']
_AFFECTED_FILE_OPTS  = ['图纸', '模具', 'QC检验图', '包装标准', '作业指导书', '材料比较单', 'BOM', '品检规范', '其他']


# ── 生成 ECR xlsx ──────────────────────────────────────

def build_ecr_xlsx(d: dict, changes=None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = '变更申请单'

    # 列宽在内容写完后统一自动调整（见文件末尾 _auto_col_widths 调用）

    # 行高（固定行）
    for r, h in {1:14, 2:26, 3:20, 4:18, 5:18, 6:16, 7:36, 8:16, 9:56, 10:16, 11:16, 12:16}.items():
        ws.row_dimensions[r].height = h

    f_normal = _font()
    f_bold   = _font(bold=True)
    f_title  = _font(size=16, bold=True)
    f_small  = _font(size=9)
    f_th     = _font(size=9, bold=True)
    f_detail = _font(size=9)
    a_center = _align('center')
    a_left   = _align('left')
    a_left_w = _align('left', wrap=True)
    a_right  = _align('right')

    # 第 1 行：文件编号
    _merge(ws, 1, 1, 1, 18, '2M2-QM-25-01-A1', font=f_small, align=a_right)
    for c in range(1, 19):
        ws.cell(1, c).border = Border()

    # 第 2 行：标题
    _merge(ws, 2, 1, 2, 18, '变 更 申 请 单', font=f_title, align=a_center)
    for c in range(1, 19):
        ws.cell(2, c).border = Border()

    # 第 3 行：基本信息
    issuing_unit       = d.get('issuing_unit', '')
    change_type        = d.get('change_type', '')
    change_type_custom = d.get('change_type_custom', '')
    change_type_text   = _mark(['设计变更', '制程变更', '其他'], change_type, change_type_custom)

    # 发出单位值缩为 1 列，其余左移一格，变更类型值扩至 4 列（14-17）
    _merge(ws, 3, 1,  3, 1,  '发出单位', font=f_bold,   align=a_center, fill=FILL_HEADER)
    _merge(ws, 3, 2,  3, 2,  issuing_unit, font=f_normal, align=a_left)
    _merge(ws, 3, 3,  3, 3,  '日期',      font=f_bold,   align=a_center, fill=FILL_HEADER)
    _merge(ws, 3, 4,  3, 5,  d.get('date', ''), font=f_normal, align=a_center)
    _merge(ws, 3, 6,  3, 6,  '变更编码',  font=f_bold,   align=a_center, fill=FILL_HEADER)
    _merge(ws, 3, 7,  3, 8,  d.get('ecr_code', ''), font=f_normal, align=a_center)
    _merge(ws, 3, 9,  3, 9,  '变更项目',  font=f_bold,   align=a_center, fill=FILL_HEADER)
    _merge(ws, 3, 10, 3, 13, d.get('project', ''), font=f_normal, align=a_left)
    _merge(ws, 3, 14, 3, 14, '变更类型',  font=f_bold,   align=a_center, fill=FILL_HEADER)
    _merge(ws, 3, 15, 3, 18, change_type_text, font=f_normal, align=a_left_w)

    # 第 4 行：分发单位
    dist_opts = ['研发', '业务', '采购', '生产', '生管', '品牌', '服务', '品管']
    _merge(ws, 4, 1, 4, 2,  '分发单位', font=f_bold,  align=a_center, fill=FILL_HEADER)
    _merge(ws, 4, 3, 4, 18, _mark(dist_opts, d.get('distribution', [])), font=f_normal, align=a_left)

    # 第 5 行：变更原因
    reason_opts          = ['品质不良', '价格变动', '设计优化', '结构优化', '成本优化', '工艺优化', '其他']
    change_reason        = d.get('change_reason', '')
    change_reason_custom = d.get('change_reason_custom', '')
    reason_text          = _mark(reason_opts, change_reason, change_reason_custom)
    _merge(ws, 5, 1, 5, 2,  '变更原因', font=f_bold,  align=a_center, fill=FILL_HEADER)
    _merge(ws, 5, 3, 5, 18, reason_text, font=f_normal, align=a_left)

    # 第 6-9 行：变更主题 + 变更内容说明
    _merge(ws, 6, 1, 6, 18, '变更主题：', font=f_bold, align=a_left, fill=FILL_HEADER)
    _merge(ws, 7, 1, 7, 18, d.get('change_subject', ''), font=f_normal, align=a_left_w)
    _merge(ws, 8, 1, 8, 18, '变更内容说明（详细说明更改哪些内容）：', font=f_bold, align=a_left, fill=FILL_HEADER)
    _merge(ws, 9, 1, 9, 18, d.get('change_desc', ''), font=f_normal, align=a_left_w)

    # 第 10 行：变更明细标签
    _merge(ws, 10, 1, 10, 18, '变更明细：', font=f_bold, align=a_left, fill=FILL_HEADER)

    # 第 11-12 行：明细表头
    def th(r1, c1, r2, c2, val):
        _merge(ws, r1, c1, r2, c2, val, font=f_th, align=a_center, fill=FILL_HEADER)

    # 列布局（共18列）：序1 主件图号2 图号3 层次4 品名5-6 规格7-8 变更方式9 取替代10 各部门11-16 处置方式17 责任人18
    th(11, 1,  12, 1,  '序号')
    th(11, 2,  12, 2,  '主件图号')
    th(11, 3,  12, 3,  '图号')
    th(11, 4,  12, 4,  '层次')
    th(11, 5,  12, 6,  '品名')
    th(11, 7,  12, 8,  '规格')
    th(11, 9,  12, 9,  '变更方式')
    th(11, 10, 12, 10, '取替代关系\n（原材料、半成品）')
    _merge(ws, 11, 11, 11, 16, '各部门问题反馈', font=f_th, align=a_center, fill=FILL_HEADER)
    for label, col in [('研发',11),('采购',12),('品管',13),('生管',14),('生产',15),('服务',16)]:
        _merge(ws, 12, col, 12, col, label, font=f_th, align=a_center, fill=FILL_HEADER)
    th(11, 17, 12, 17, '处置方式')
    th(11, 18, 12, 18, '责任人')

    # 第 13+ 行：明细数据（有比对结果则填充，否则留 6 行空行）
    detail_data = changes or []
    n_rows      = max(len(detail_data), 6)

    # 预扫描：找出 cancel+add 对，记录 {cancel行索引: change_kind}
    rd_merge_map = {}   # cancel_i -> change_kind
    rd_skip_set  = set()  # add_i（取替代关系列已被合并，跳过）
    j = 0
    while j < len(detail_data):
        if (detail_data[j].get('row_type') == 'cancel'
                and j + 1 < len(detail_data)
                and detail_data[j + 1].get('row_type') == 'add'):
            rd_merge_map[j] = detail_data[j].get('change_kind', '')
            rd_skip_set.add(j + 1)
            j += 2
        else:
            j += 1

    for i in range(n_rows):
        r = 13 + i
        ws.row_dimensions[r].height = 18
        for c in range(1, 19):
            ws.cell(row=r, column=c).border = BORDER_ALL

        if i < len(detail_data):
            ch       = detail_data[i]
            row_type = ch.get('row_type', '')
            row_fill = FILL_CANCEL if row_type in ('cancel', 'deleted') else None

            def _dc(col, val, al=None, _r=r, _fill=row_fill):
                cell = ws.cell(row=_r, column=col, value=val)
                cell.font      = f_detail
                cell.alignment = al or a_center
                if _fill:
                    cell.fill = _fill
                return cell

            # 取消行：对所有单元格（含合并区域内的空格）统一着色
            if row_fill:
                for c in range(1, 19):
                    ws.cell(row=r, column=c).fill = row_fill

            _dc(1, ch.get('seq', i + 1))
            _dc(2, ch.get('main_drawing', ''))        # 主件图号
            _dc(3, ch.get('drawing',      ''))        # 图号
            _dc(4, ch.get('level',        ''))        # 层次
            _merge(ws, r, 5, r, 6, ch.get('name', ''), font=f_detail, align=a_left, fill=row_fill)   # 品名（5-6合并）
            _merge(ws, r, 7, r, 8, ch.get('spec', ''), font=f_detail, align=a_left, fill=row_fill)   # 规格（7-8合并）
            _dc(9, ch.get('change_method', ''), a_left)

            # 取替代关系列（col 10）：cancel+add 对合并两行并填变更类型；单行填 qty_desc 或 change_kind
            if i in rd_merge_map:
                kind_text = rd_merge_map[i]
                _merge(ws, r, 10, r + 1, 10, kind_text, font=f_detail, align=a_center)
            elif i not in rd_skip_set:
                _dc(10, ch.get('qty_desc') or ch.get('change_kind', ''))

    # 填写人员行（紧接明细末尾）
    submitter_row = 13 + n_rows
    ws.row_dimensions[submitter_row].height = 16
    submitter = d.get('submitter', issuing_unit)
    _merge(ws, submitter_row, 1, submitter_row, 18,
           f'填写人员：{submitter}', font=f_normal, align=a_right)

    # Logo（左上角，锚定 A1）
    _logo_path = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '..', '..', '..', 'src', 'assets', 'logo-banner.png'
    ))
    if os.path.exists(_logo_path):
        try:
            from openpyxl.drawing.image import Image as XlImage
            img = XlImage(_logo_path)
            img.width  = 110
            img.height = 30
            from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
            from openpyxl.drawing.xdr import XDRPositiveSize2D
            _EPX = 9525   # EMU per pixel (96 DPI)
            marker = AnchorMarker(col=0, colOff=5 * _EPX, row=0, rowOff=3 * _EPX)
            img.anchor = OneCellAnchor(_from=marker,
                                       ext=XDRPositiveSize2D(cx=img.width * _EPX, cy=img.height * _EPX))
            ws.add_image(img)
        except Exception:
            pass

    # 根据实际内容自动调整列宽
    _auto_col_widths(ws)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ── 生成 ECN xlsx ──────────────────────────────────────

def build_ecn_xlsx(d: dict, changes=None) -> bytes:
    """生成变更通知单 xlsx
    列布局（12列 A-L）：
    A(1) : 标签列（信息行）/ 序号（明细行）
    B-C(2-3) : 主件图号（合并）
    D-E(4-5) : 图号（合并）
    F-G(6-7) : 品名（合并）
    H-I(8-9) : 规格（合并）
    J(10): 处理意见（导入方式选项）
    K(11): 负责人
    L(12): 备注
    """
    wb = Workbook()
    ws = wb.active
    ws.title = '变更通知单'
    NC = 15  # 共15列：序号|主件图号(2)|图号(2)|层次|品名(2)|规格(2)|变更方式|取替代关系|处理意见|负责人|备注

    f_normal = _font()
    f_bold   = _font(bold=True)
    f_title  = _font(size=16, bold=True)
    f_small  = _font(size=9)
    f_th     = _font(size=9, bold=True)
    f_detail = _font(size=9)
    a_center = _align('center')
    a_left   = _align('left')
    a_left_w = _align('left', wrap=True)
    a_right  = _align('right')

    # 行高
    for r, h in {1:14, 2:26, 3:18, 4:18, 5:18, 6:18, 7:48, 8:36, 9:24}.items():
        ws.row_dimensions[r].height = h

    # 第1行：文件编号
    _merge(ws, 1, 1, 1, NC, '2M2-QM-25-03-A2', font=f_small, align=a_right)
    for c in range(1, NC + 1):
        ws.cell(1, c).border = Border()

    # 第2行：标题
    _merge(ws, 2, 1, 2, NC, '变 更 通 知 单', font=f_title, align=a_center)
    for c in range(1, NC + 1):
        ws.cell(2, c).border = Border()

    # 第3行：基本信息
    issuing_unit = d.get('issuing_unit', '')
    product      = d.get('product', d.get('project', ''))
    date_str     = d.get('date', '')
    ecn_code     = d.get('ecn_code', '')
    responsible  = d.get('responsible', '')

    # 列分配（共15列）：发出单位(1)|值(2-3)|产品型号(4)|值(5-7)|负责人(8)|值(9-10)|日期(11)|值(12)|ECN编号(13-15)
    _merge(ws, 3, 1,  3, 1,  '发出单位', font=f_bold,   align=a_center, fill=FILL_HEADER)
    _merge(ws, 3, 2,  3, 3,  issuing_unit, font=f_normal, align=a_left)
    _merge(ws, 3, 4,  3, 4,  '产品型号', font=f_bold,   align=a_center, fill=FILL_HEADER)
    _merge(ws, 3, 5,  3, 7,  product,      font=f_normal, align=a_left)
    _merge(ws, 3, 8,  3, 8,  '负责人',   font=f_bold,   align=a_center, fill=FILL_HEADER)
    _merge(ws, 3, 9,  3, 10, responsible,  font=f_normal, align=a_left)
    _merge(ws, 3, 11, 3, 11, '日期',     font=f_bold,   align=a_center, fill=FILL_HEADER)
    _merge(ws, 3, 12, 3, 12, date_str,    font=f_normal, align=a_center)
    _merge(ws, 3, 13, 3, NC, ecn_code,    font=f_bold,   align=a_center, fill=FILL_HEADER)

    # 通用信息行：标签列(1) + 内容列(2-NC)
    def _info_row(r, label, value, wrap=False):
        _merge(ws, r, 1, r, 1, label, font=f_bold, align=a_center, fill=FILL_HEADER)
        _merge(ws, r, 2, r, NC, value,
               font=f_normal, align=(_align('left', wrap=True) if wrap else a_left))

    import_meth   = d.get('import_method', '')
    distribution  = d.get('distribution', [])
    change_reason = d.get('change_reason', '')
    cr_custom     = d.get('change_reason_custom', '')
    affected      = d.get('affected_files', [])

    # 第4行：导入方式
    _info_row(4, '导入方式', _mark(_IMPORT_OPTS, import_meth))
    # 第5行：分发单位
    dist_opts = ['研发', '业务', '采购', '生产', '生管', '品牌', '服务', '品管']
    _info_row(5, '分发单位', _mark(dist_opts, distribution))
    # 第6行：变更原因
    reason_opts = ['品质不良', '价格变动', '设计优化', '结构优化', '成本优化', '工艺优化', '其他']
    _info_row(6, '变更原因', _mark(reason_opts, change_reason, cr_custom))
    # 第7行：变更内容说明
    _info_row(7, '变更内容', d.get('change_desc', ''), wrap=True)
    # 第8行：影响文件
    _info_row(8, '影响文件', _mark(_AFFECTED_FILE_OPTS, affected), wrap=True)

    responsible = d.get('responsible', '')

    # 第9行：明细表头
    def _th(c1, c2, val):
        _merge(ws, 9, c1, 9, c2, val, font=f_th, align=a_center, fill=FILL_HEADER)

    _th(1,  1,  '序号')
    _th(2,  3,  '主件图号')
    _th(4,  5,  '图号')
    _th(6,  6,  '层次')
    _th(7,  8,  '品名')
    _th(9,  10, '规格')
    _th(11, 11, '变更方式')
    _th(12, 12, '取替代关系')
    _th(13, 13, '处理意见')
    _th(14, 14, '负责人')
    _th(15, 15, '备注')

    # 明细数据行
    detail_data = changes or []
    n_rows      = max(len(detail_data), 5)

    # 预扫描：找出 cancel+add 对，取替代关系列需跨两行合并
    sub_merge_map = {}   # cancel_i -> 取替代关系文本
    sub_skip_set  = set()  # add_i（已被合并，跳过写入）
    j = 0
    while j < len(detail_data):
        if (detail_data[j].get('row_type') == 'cancel'
                and j + 1 < len(detail_data)
                and detail_data[j + 1].get('row_type') == 'add'):
            ch_j = detail_data[j]
            sub_merge_map[j] = ch_j.get('substitution') or ch_j.get('qty_desc') or ch_j.get('change_kind', '')
            sub_skip_set.add(j + 1)
            j += 2
        else:
            j += 1

    for i in range(n_rows):
        r = 10 + i
        ws.row_dimensions[r].height = 18
        for c in range(1, NC + 1):
            ws.cell(row=r, column=c).border = BORDER_ALL

        if i >= len(detail_data):
            continue

        ch       = detail_data[i]
        row_type = ch.get('row_type', '')
        row_fill = FILL_CANCEL if row_type in ('cancel', 'deleted') else None

        if row_fill:
            for c in range(1, NC + 1):
                ws.cell(row=r, column=c).fill = row_fill

        def _dc(col, val, al=None, _r=r, _fill=row_fill):
            cell = ws.cell(row=_r, column=col, value=val)
            cell.font      = f_detail
            cell.alignment = al or a_center
            if _fill:
                cell.fill = _fill
            return cell

        _dc(1, ch.get('seq', i + 1))
        _merge(ws, r, 2,  r, 3,  ch.get('main_drawing', ''), font=f_detail, align=a_center, fill=row_fill)
        _merge(ws, r, 4,  r, 5,  ch.get('drawing', ''),      font=f_detail, align=a_center, fill=row_fill)
        _dc(6, ch.get('level', ''), a_center)                             # 层次
        _merge(ws, r, 7,  r, 8,  ch.get('name', ''),         font=f_detail, align=a_left,   fill=row_fill)
        _merge(ws, r, 9,  r, 10, ch.get('spec', ''),         font=f_detail, align=a_left,   fill=row_fill)
        _dc(11, ch.get('change_method', ''), a_center)                    # 变更方式
        # 取替代关系（col 12）：cancel+add 对合并两行；单行直接写
        if i in sub_merge_map:
            _merge(ws, r, 12, r + 1, 12, sub_merge_map[i], font=f_detail, align=a_center)
        elif i not in sub_skip_set:
            _dc(12, ch.get('substitution') or ch.get('qty_desc') or ch.get('change_kind', ''), a_center)
        _dc(13, ch.get('handling', ''), a_center)                         # 处理意见
        _dc(14, ch.get('responsible_person', ''), a_center)               # 负责人
        _dc(15, '', a_left)                                                # 备注（空白）

    # ── 页脚区（按图片布局）─────────────────────────────
    # 列分区：col1-2=标签 | col3-4=生产 | col5-6=服务 | col7-9=品管 | col10-11=生管 | col12-13=研发 | col14-15=空余
    footer = 10 + n_rows

    f_dept  = _font(size=9, bold=True)
    a_ctr_w = _align('center', wrap=True)

    # ── 行 1/2：品管追踪记录（标签跨2行）+ 部门名称行 ──
    qt = footer
    ws.row_dimensions[qt].height   = 20
    ws.row_dimensions[qt + 1].height = 20

    # 标签：跨2行、2列
    _merge(ws, qt, 1, qt + 1, 2, '品管\n追踪记录', font=f_dept, align=a_ctr_w, fill=FILL_HEADER)

    # 部门名称（第1行）
    _merge(ws, qt, 3,  qt, 4,  '生  产', font=f_dept, align=a_center, fill=FILL_HEADER)
    _merge(ws, qt, 5,  qt, 6,  '服  务', font=f_dept, align=a_center, fill=FILL_HEADER)
    _merge(ws, qt, 7,  qt, 9,  '品  管', font=f_dept, align=a_center, fill=FILL_HEADER)
    _merge(ws, qt, 10, qt, 11, '生  管', font=f_dept, align=a_center, fill=FILL_HEADER)
    _merge(ws, qt, 12, qt, 13, '研  发', font=f_dept, align=a_center, fill=FILL_HEADER)
    _merge(ws, qt, 14, qt, NC, '',        font=f_normal, align=a_center)

    # 签名空白（第2行，对应各部门）
    for c1, c2 in [(3, 4), (5, 6), (10, 11), (12, 13), (14, NC)]:
        _merge(ws, qt + 1, c1, qt + 1, c2, '', font=f_normal, align=a_center)
    _merge(ws, qt + 1, 7, qt + 1, 9, '', font=f_normal, align=a_center)

    # ── 行 3：确认日期 ──
    cd = qt + 2
    ws.row_dimensions[cd].height = 18
    _merge(ws, cd, 1,  cd, 2,  '确认日期', font=f_dept, align=a_center, fill=FILL_HEADER)
    for c1, c2 in [(3, 4), (5, 6), (10, 11), (12, 13), (14, NC)]:
        _merge(ws, cd, c1, cd, c2, '', font=f_normal, align=a_center)
    _merge(ws, cd, 7, cd, 9, '', font=f_normal, align=a_center)

    # ── 行 4：备注 ──
    nr = cd + 1
    ws.row_dimensions[nr].height = 28
    _merge(ws, nr, 1,  nr, 2,  '备  注', font=f_dept, align=a_center, fill=FILL_HEADER)
    _merge(ws, nr, 3,  nr, NC, '',        font=f_normal, align=a_left)

    # ── 行 5：结案 ──
    ar = nr + 1
    ws.row_dimensions[ar].height = 18
    _merge(ws, ar, 1,  ar, 2,  '结  案', font=f_dept, align=a_center, fill=FILL_HEADER)
    _merge(ws, ar, 3,  ar, 8,  '',        font=f_normal, align=a_left)
    _merge(ws, ar, 9,  ar, 12, '品管签名：', font=f_normal, align=a_left)
    _merge(ws, ar, 13, ar, NC, '日期：',     font=f_normal, align=a_left)

    # Logo
    _logo_path = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '..', '..', '..', 'src', 'assets', 'logo-banner.png'
    ))
    if os.path.exists(_logo_path):
        try:
            from openpyxl.drawing.image import Image as XlImage
            img = XlImage(_logo_path)
            img.width  = 110
            img.height = 30
            from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
            from openpyxl.drawing.xdr import XDRPositiveSize2D
            _EPX = 9525   # EMU per pixel (96 DPI)
            marker = AnchorMarker(col=0, colOff=5 * _EPX, row=0, rowOff=3 * _EPX)
            img.anchor = OneCellAnchor(_from=marker,
                                       ext=XDRPositiveSize2D(cx=img.width * _EPX, cy=img.height * _EPX))
            ws.add_image(img)
        except Exception:
            pass

    _auto_col_widths(ws)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
def _parse_checked_text(text, opts):
    """从 ☑/☐ 标记文本中提取已选项"""
    selected = []
    for opt in opts:
        if f'☑ {opt}' in text or f'☑{opt}' in text:
            selected.append(opt)
    return selected


def parse_ecr_rows_xlsx(ws):
    """用 openpyxl 读取 ECR xlsx 明细行，返回 (fields_dict, changes_list)"""
    def _v(r, c):
        return str(ws.cell(r, c).value or '').strip()

    dist_opts   = ['研发', '业务', '采购', '生产', '生管', '品牌', '服务', '品管']
    reason_opts = ['品质不良', '价格变动', '设计优化', '结构优化', '成本优化', '工艺优化', '其他']
    type_opts   = ['设计变更', '制程变更', '其他']

    issuing_unit   = _v(3, 2)
    date_val       = _v(3, 4)
    ecr_code       = _v(3, 7)
    project        = _v(3, 10)
    ct_text        = _v(3, 15)
    distribution   = _parse_checked_text(_v(4, 3), dist_opts)
    reason_list    = _parse_checked_text(_v(5, 3), reason_opts)
    change_reason  = reason_list[0] if reason_list else ''
    type_list      = _parse_checked_text(ct_text, type_opts)
    change_type    = type_list[0] if type_list else ''
    change_subject = _v(7, 1)
    change_desc    = _v(9, 1)

    changes = []
    for r in range(13, ws.max_row + 1):
        seq_val = ws.cell(r, 1).value
        if seq_val is None:
            break
        drawing      = str(ws.cell(r, 3).value or '').strip()
        main_drawing = str(ws.cell(r, 2).value or '').strip()
        if not drawing and not main_drawing:
            continue

        fill_rgb = ''
        try:
            fill = ws.cell(r, 1).fill
            if fill and fill.fill_type == 'solid':
                fill_rgb = fill.fgColor.rgb or ''
        except Exception:
            pass
        is_cancel_row = 'FDECEA' in fill_rgb.upper()

        change_method = str(ws.cell(r, 9).value or '').strip()
        change_kind   = str(ws.cell(r, 11).value or '').strip()
        level         = str(ws.cell(r, 4).value or '').strip()
        name          = str(ws.cell(r, 5).value or '').strip()
        spec          = str(ws.cell(r, 7).value or '').strip()

        try:
            seq = int(float(seq_val))
        except (TypeError, ValueError):
            seq = len(changes) + 1

        if is_cancel_row:
            row_type = 'cancel' if change_method == '取消' else 'deleted'
        else:
            row_type = 'add' if change_method == '新增' else 'added'

        substitution       = str(ws.cell(r, 10).value or '').strip()
        handling           = str(ws.cell(r, 17).value or '').strip()
        responsible_person = str(ws.cell(r, 18).value or '').strip()

        changes.append({
            'seq': seq, 'level': level, 'main_drawing': main_drawing,
            'drawing': drawing, 'name': name, 'spec': spec,
            'change_method': change_method, 'change_kind': change_kind,
            'substitution': substitution,
            'handling': handling, 'responsible_person': responsible_person,
            'row_type': row_type,
        })

    # 填写人员：在明细区末尾查找"填写人员：xxx"格式
    submitter = ''
    for r in range(13, ws.max_row + 1):
        v = str(ws.cell(r, 1).value or '').strip()
        if v.startswith('填写人员：'):
            submitter = v[len('填写人员：'):].strip()
            break

    return {
        'issuing_unit': issuing_unit, 'date': date_val,
        'ecr_code': ecr_code, 'project': project,
        'change_type': change_type, 'distribution': distribution,
        'change_reason': change_reason, 'change_subject': change_subject,
        'change_desc': change_desc, 'submitter': submitter,
    }, changes


def parse_ecr_rows_xls(ws):
    """用 xlrd 读取 ECR xls 明细行，返回 (fields_dict, changes_list)"""
    def _v(r, c):
        try:
            v = ws.cell_value(r, c)
            return str(int(v)) if isinstance(v, float) and v == int(v) else str(v or '').strip()
        except Exception:
            return ''

    dist_opts   = ['研发', '业务', '采购', '生产', '生管', '品牌', '服务', '品管']
    reason_opts = ['品质不良', '价格变动', '设计优化', '结构优化', '成本优化', '工艺优化', '其他']
    type_opts   = ['设计变更', '制程变更', '其他']

    # xls 行列从 0 开始，对应 xlsx 的行r减1、列c减1
    issuing_unit   = _v(2, 1)   # row3,col2
    date_val       = _v(2, 3)   # row3,col4
    ecr_code       = _v(2, 6)   # row3,col7
    project        = _v(2, 9)   # row3,col10
    ct_text        = _v(2, 14)  # row3,col15
    distribution   = _parse_checked_text(_v(3, 2), dist_opts)
    reason_list    = _parse_checked_text(_v(4, 2), reason_opts)
    change_reason  = reason_list[0] if reason_list else ''
    type_list      = _parse_checked_text(ct_text, type_opts)
    change_type    = type_list[0] if type_list else ''
    change_subject = _v(6, 0)   # row7,col1
    change_desc    = _v(8, 0)   # row9,col1

    changes = []
    for r in range(12, ws.nrows):  # row13 = index 12
        seq_raw = ws.cell_value(r, 0)
        if seq_raw == '' or seq_raw is None:
            break
        drawing      = str(ws.cell_value(r, 2) or '').strip()
        main_drawing = str(ws.cell_value(r, 1) or '').strip()
        if not drawing and not main_drawing:
            continue

        change_method      = str(ws.cell_value(r, 8)  or '').strip()
        substitution       = str(ws.cell_value(r, 9)  or '').strip()
        change_kind        = str(ws.cell_value(r, 10) or '').strip()
        level              = str(ws.cell_value(r, 3)  or '').strip()
        name               = str(ws.cell_value(r, 4)  or '').strip()
        spec               = str(ws.cell_value(r, 6)  or '').strip()
        handling           = str(ws.cell_value(r, 16) or '').strip()
        responsible_person = str(ws.cell_value(r, 17) or '').strip()

        try:
            seq = int(float(seq_raw))
        except (TypeError, ValueError):
            seq = len(changes) + 1

        # xls 无填充色信息可直接读，通过变更方式判断行类型
        row_type = 'cancel' if change_method == '取消' else (
                   'deleted' if change_method == '取消' else (
                   'add' if change_method == '新增' else 'added'))

        changes.append({
            'seq': seq, 'level': level, 'main_drawing': main_drawing,
            'drawing': drawing, 'name': name, 'spec': spec,
            'change_method': change_method, 'change_kind': change_kind,
            'substitution': substitution,
            'handling': handling, 'responsible_person': responsible_person,
            'row_type': row_type,
        })

    # 填写人员：在明细区末尾查找"填写人员：xxx"格式（xls 行索引从0开始）
    submitter = ''
    for r in range(12, ws.nrows):
        v = str(ws.cell_value(r, 0) or '').strip()
        if v.startswith('填写人员：'):
            submitter = v[len('填写人员：'):].strip()
            break

    return {
        'issuing_unit': issuing_unit, 'date': date_val,
        'ecr_code': ecr_code, 'project': project,
        'change_type': change_type, 'distribution': distribution,
        'change_reason': change_reason, 'change_subject': change_subject,
        'change_desc': change_desc, 'submitter': submitter,
    }, changes
