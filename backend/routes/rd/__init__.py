from flask import Blueprint, request, Response
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter
import io, urllib.parse, os, re

rd_bp = Blueprint('rd', __name__)

# ── 样式常量 ──────────────────────────────────────────

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


_BOM_REQUIRED_COLS = ['层次', '图号', '品名', '规格', '数量', '单位', '状态']

def _validate_bom(path, role='before'):
    """校验 BOM 文件合法性，返回错误消息字符串；无误返回 None。
    role='before'：变更前文件，要求状态列全部为「已发布」
    role='after' ：变更审核中文件，要求状态列不能全是「已发布」
    """
    from openpyxl import load_workbook
    try:
        wb = load_workbook(path, data_only=True, read_only=True)
    except Exception as e:
        label = '变更前文件' if role == 'before' else '变更审核中文件'
        return f'{label}无法读取：{e}'
    ws = wb.active

    # 1. 列名核验
    col_map = {}
    for c in range(1, ws.max_column + 1):
        h = ws.cell(1, c).value
        if h is not None:
            col_map[str(h).strip()] = c
    missing = [col for col in _BOM_REQUIRED_COLS if col not in col_map]
    label = '变更前文件' if role == 'before' else '变更审核中文件'
    if missing:
        wb.close()
        return f'{label}缺少必要列：{", ".join(missing)}'

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

    if role == 'before':
        not_published = [s for s in statuses if s != '已发布']
        if not_published:
            return (f'变更前文件中存在非「已发布」状态的物料（共 {len(not_published)} 行），'
                    f'例如：{not_published[0]}。变更前BOM应全部为已发布状态')
    else:  # after
        if all(s == '已发布' for s in statuses):
            return '变更审核中文件的状态列全部为「已发布」，该文件应包含处于审核中状态的物料'

    return None


def _parse_bom(path):
    """读取并清洗 BOM 文件，返回 {(层次, 编码): item} 字典"""
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True)
    ws = wb.active

    # 表头 → 列号映射
    col_map = {}
    for c in range(1, ws.max_column + 1):
        h = ws.cell(1, c).value
        if h is not None:
            col_map[str(h).strip()] = c

    def _get(row, name, default=''):
        c = col_map.get(name)
        return ws.cell(row, c).value if c else default

    items = {}
    for r in range(2, ws.max_row + 1):
        level   = _level_str(_get(r, '层次'))
        drawing = str(_get(r, '图号') or '').strip()

        # 清洗：跳过无层次或无图号的行
        if not level or not drawing:
            continue

        # 以最后一个"-"分割编码和版本
        idx = drawing.rfind('-')
        code    = drawing[:idx]  if idx > 0 else drawing
        version = drawing[idx+1:] if idx > 0 else ''

        # 清洗：跳过编码为空的行（图号格式异常）
        if not code:
            continue

        # 清洗：过滤编码含"."的项、以"14ST10"开头的项
        if '.' in code or code.startswith('14ST10'):
            continue

        qty_raw = _get(r, '数量', 1)
        try:
            qty = float(qty_raw)
        except (TypeError, ValueError):
            qty = 1.0

        raw_spec = str(_get(r, '规格') or '').strip()
        items[(level, code)] = {
            'level':   level,
            'code':    code,
            'version': version,
            'drawing': drawing,
            'name':    str(_get(r, '品名') or '').strip(),
            'spec':    _complete_spec_version(raw_spec, version),
            'qty':     qty,
            'unit':    str(_get(r, '单位') or 'PCS').strip(),
            'status':  str(_get(r, '状态') or '').strip(),
        }
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
    if status not in ('通用变更审核中', '非通用变更审核中'):
        return item['drawing']
    is_non_common = (status == '非通用变更审核中')
    new_ver = _next_version(item['version'], is_non_common)
    return f"{item['code']}-{new_ver}"


def _update_spec_version(spec, old_ver, new_ver):
    """将规格字符串中 -旧版本号 替换为 -新版本号（避免误替换普通文字）"""
    if not spec or not old_ver or not new_ver or old_ver == new_ver:
        return spec
    return spec.replace(f'-{old_ver}', f'-{new_ver}')


def _compare_bom(before_path, after_path):
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

    # 按层次排序（深度优先）
    all_keys = sorted(
        set(before) | set(after),
        key=lambda k: _level_sort_key(k[0])
    )

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
            is_ecr = a['status'] in ('通用变更审核中', '非通用变更审核中')
            qty_changed = abs(b['qty'] - a['qty']) > 1e-9

            if not (is_ecr or qty_changed):
                continue  # 无变化，跳过

            n_version += 1
            is_non_common = (a['status'] == '非通用变更审核中')
            kind = ('非通用变更' if is_non_common else '通用变更') if is_ecr else '数量变更'

            # 旧版本（审核中 BOM 中的当前图号，即未发布的旧图号）
            old_drawing = a['drawing']
            old_version = a['version']

            # 推算新版本
            new_version = _next_version(old_version, is_non_common) if is_ecr else old_version
            new_drawing = f"{a['code']}-{new_version}" if is_ecr else old_drawing
            new_spec    = _update_spec_version(a['spec'], old_version, new_version)

            # 取消行：取消旧版本，主件图号为 after 父级当前图号，数量用 before 的旧数量
            changes.append({
                'row_type':      'cancel',
                'change_kind':   kind,
                'level':         key[0],
                'main_drawing':  _old_main_drawing(a['level']),
                'drawing':       old_drawing,
                'name':          a['name'],
                'spec':          a['spec'],
                'qty':           b['qty'],
                'change_method': '取消',
            })
            # 新增行：新增新版本，主件图号为 after 父级推算后的新图号
            changes.append({
                'row_type':      'add',
                'change_kind':   kind,
                'level':         key[0],
                'main_drawing':  _new_main_drawing(a['level']),
                'drawing':       new_drawing,
                'name':          a['name'],
                'spec':          new_spec,
                'qty':           a['qty'],
                'change_method': '新增',
            })

        elif in_b:
            # 仅在 before 中存在（已删除）
            b = before[key]
            n_deleted += 1
            changes.append({
                'row_type':      'deleted',
                'change_kind':   '删除',
                'level':         key[0],
                'main_drawing':  _before_main_drawing(b['level']),
                'drawing':       b['drawing'],
                'name':          b['name'],
                'spec':          b['spec'],
                'qty':           b['qty'],
                'change_method': '取消',
            })

        else:
            # 仅在 after 中存在（新增）
            a = after[key]
            n_added += 1
            is_ecr_new    = a['status'] in ('通用变更审核中', '非通用变更审核中')
            is_non_common = (a['status'] == '非通用变更审核中')
            old_version   = a['version']
            new_version   = _next_version(old_version, is_non_common) if is_ecr_new else old_version
            new_drawing   = f"{a['code']}-{new_version}" if is_ecr_new else a['drawing']
            new_spec      = _update_spec_version(a['spec'], old_version, new_version)
            changes.append({
                'row_type':      'added',
                'change_kind':   '新增',
                'level':         key[0],
                'main_drawing':  _new_main_drawing(a['level']),
                'drawing':       new_drawing,
                'name':          a['name'],
                'spec':          new_spec,
                'qty':           a['qty'],
                'change_method': '新增',
            })

    for i, ch in enumerate(changes):
        ch['seq'] = i + 1

    stats = {
        'version': n_version,
        'added':   n_added,
        'deleted': n_deleted,
        'total':   len(changes),
    }
    return {'changes': changes, 'stats': stats}


# ── 生成 ECR xlsx ──────────────────────────────────────

def _build_ecr_xlsx(d: dict, changes=None) -> bytes:
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
    _merge(ws, 1, 1, 1, 17, '2M2-QM-25-01-A1', font=f_small, align=a_right)
    for c in range(1, 18):
        ws.cell(1, c).border = Border()

    # 第 2 行：标题
    _merge(ws, 2, 1, 2, 17, '变 更 申 请 单', font=f_title, align=a_center)
    for c in range(1, 18):
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
    _merge(ws, 3, 15, 3, 17, change_type_text, font=f_normal, align=a_left_w)

    # 第 4 行：分发单位
    dist_opts = ['研发', '业务', '采购', '生产', '生管', '品牌', '服务', '品管']
    _merge(ws, 4, 1, 4, 2,  '分发单位', font=f_bold,  align=a_center, fill=FILL_HEADER)
    _merge(ws, 4, 3, 4, 17, _mark(dist_opts, d.get('distribution', [])), font=f_normal, align=a_left)

    # 第 5 行：变更原因
    reason_opts          = ['品质不良', '价格变动', '设计优化', '结构优化', '成本优化', '工艺优化', '其他']
    change_reason        = d.get('change_reason', '')
    change_reason_custom = d.get('change_reason_custom', '')
    reason_text          = _mark(reason_opts, change_reason, change_reason_custom)
    _merge(ws, 5, 1, 5, 2,  '变更原因', font=f_bold,  align=a_center, fill=FILL_HEADER)
    _merge(ws, 5, 3, 5, 17, reason_text, font=f_normal, align=a_left)

    # 第 6-9 行：变更主题 + 变更内容说明
    _merge(ws, 6, 1, 6, 17, '变更主题：', font=f_bold, align=a_left, fill=FILL_HEADER)
    _merge(ws, 7, 1, 7, 17, d.get('change_subject', ''), font=f_normal, align=a_left_w)
    _merge(ws, 8, 1, 8, 17, '变更内容说明（详细说明更改哪些内容）：', font=f_bold, align=a_left, fill=FILL_HEADER)
    _merge(ws, 9, 1, 9, 17, d.get('change_desc', ''), font=f_normal, align=a_left_w)

    # 第 10 行：变更明细标签
    _merge(ws, 10, 1, 10, 17, '变更明细：', font=f_bold, align=a_left, fill=FILL_HEADER)

    # 第 11-12 行：明细表头
    def th(r1, c1, r2, c2, val):
        _merge(ws, r1, c1, r2, c2, val, font=f_th, align=a_center, fill=FILL_HEADER)

    th(11, 1,  12, 1,  '序号')
    th(11, 2,  12, 2,  '主件图号')
    th(11, 3,  12, 3,  '图号')
    th(11, 4,  12, 5,  '品名')
    th(11, 6,  12, 7,  '规格')
    th(11, 8,  12, 8,  '变更方式')
    th(11, 9,  12, 9,  '取替代关系\n（原材料、半成品）')
    _merge(ws, 11, 10, 11, 15, '各部门问题反馈', font=f_th, align=a_center, fill=FILL_HEADER)
    for label, col in [('研发',10),('采购',11),('品管',12),('生管',13),('生产',14),('服务',15)]:
        _merge(ws, 12, col, 12, col, label, font=f_th, align=a_center, fill=FILL_HEADER)
    th(11, 16, 12, 16, '处置方式')
    th(11, 17, 12, 17, '责任人')

    # 第 13+ 行：明细数据（有比对结果则填充，否则留 6 行空行）
    detail_data = changes or []
    n_rows      = max(len(detail_data), 6)

    for i in range(n_rows):
        r = 13 + i
        ws.row_dimensions[r].height = 18
        for c in range(1, 18):
            ws.cell(row=r, column=c).border = BORDER_ALL

        if i < len(detail_data):
            ch       = detail_data[i]
            row_type = ch.get('row_type', '')
            row_fill = FILL_CANCEL if row_type == 'cancel' else None

            def _dc(col, val, al=None, _r=r, _fill=row_fill):
                cell = ws.cell(row=_r, column=col, value=val)
                cell.font      = f_detail
                cell.alignment = al or a_center
                if _fill:
                    cell.fill = _fill
                return cell

            # 取消行：对所有单元格（含合并区域内的空格）统一着色
            if row_fill:
                for c in range(1, 18):
                    ws.cell(row=r, column=c).fill = row_fill

            _dc(1, ch.get('seq', i + 1))
            _dc(2, ch.get('main_drawing', ''))        # 主件图号
            _dc(3, ch.get('drawing',      ''))        # 图号
            _merge(ws, r, 4, r, 5, ch.get('name', ''), font=f_detail, align=a_left, fill=row_fill)   # 品名（4-5合并）
            _merge(ws, r, 6, r, 7, ch.get('spec', ''), font=f_detail, align=a_left, fill=row_fill)   # 规格（6-7合并）
            _dc(8, ch.get('change_method', ''), a_left)

    # 填写人员行（紧接明细末尾）
    submitter_row = 13 + n_rows
    ws.row_dimensions[submitter_row].height = 16
    submitter = d.get('submitter', issuing_unit)
    _merge(ws, submitter_row, 1, submitter_row, 17,
           f'填写人员：{submitter}', font=f_normal, align=a_left)

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
            img.anchor = 'A1'
            ws.add_image(img)
        except Exception:
            pass

    # 根据实际内容自动调整列宽
    _auto_col_widths(ws)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ── 路由 ──────────────────────────────────────────────

@rd_bp.post('/ecr/export')
def export_ecr():
    from result import Result
    d = request.get_json() or {}
    changes = d.pop('changes', None)
    try:
        xlsx_bytes = _build_ecr_xlsx(d, changes)
    except Exception as e:
        return Result.fail(f'生成失败：{str(e)}').to_response()

    ecr_code = d.get('ecr_code', 'ECR')
    project  = d.get('project', '')
    filename = f"{ecr_code} {project} 变更申请单.xlsx".replace('/', '-')
    encoded  = urllib.parse.quote(filename)

    return Response(
        xlsx_bytes,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{encoded}",
            'Content-Length': str(len(xlsx_bytes)),
        }
    )


@rd_bp.post('/ecr/compare-bom')
def compare_bom():
    from result import Result
    d = request.get_json() or {}
    before_path = (d.get('bom_before_path') or '').strip()
    after_path  = (d.get('bom_after_path')  or '').strip()

    if not before_path or not after_path:
        return Result.fail('请先选择两个BOM文件').to_response()
    if not os.path.exists(before_path):
        return Result.fail('变更前文件不存在，请重新选择').to_response()
    if not os.path.exists(after_path):
        return Result.fail('变更审核中文件不存在，请重新选择').to_response()

    # 文件合法性校验
    err = _validate_bom(before_path, role='before')
    if err:
        return Result.fail(err).to_response()
    err = _validate_bom(after_path, role='after')
    if err:
        return Result.fail(err).to_response()

    try:
        result = _compare_bom(before_path, after_path)
        return Result.ok(result).to_response()
    except Exception as e:
        return Result.fail(f'比对失败：{str(e)}').to_response()


# ── 变更提醒 CRUD ──────────────────────────────────

def _check_rd_admin(request):
    """从请求头 X-User-Permissions 判断是否有 rd:admin 权限（前端传递），
    或从 X-User-Roles 判断是否为 admin 角色。返回 True / False。"""
    roles       = (request.headers.get('X-User-Roles', '') or '').split(',')
    permissions = (request.headers.get('X-User-Permissions', '') or '').split(',')
    return 'admin' in roles or 'rd:admin' in permissions


@rd_bp.get('/reminders')
def list_reminders():
    """返回所有在架（is_active=True）的变更提醒（所有 rd 用户可读）"""
    from result import Result
    from database.models.rd import EcrReminder
    items = EcrReminder.query.filter_by(is_active=True).order_by(EcrReminder.created_at.desc()).all()
    return Result.ok([i.to_dict() for i in items]).to_response()


@rd_bp.get('/reminders/all')
def list_reminders_all():
    """返回全部提醒（含下架历史），仅 rd:admin 可用"""
    from result import Result
    from database.models.rd import EcrReminder
    if not _check_rd_admin(request):
        return Result.fail('权限不足：需要研发部管理员权限').to_response()
    items = EcrReminder.query.order_by(EcrReminder.created_at.desc()).all()
    return Result.ok([i.to_dict() for i in items]).to_response()


@rd_bp.post('/reminders')
def create_reminder():
    """新建变更提醒，仅 rd:admin 可用"""
    from result import Result
    from database.base import db
    from database.models.rd import EcrReminder
    if not _check_rd_admin(request):
        return Result.fail('权限不足：需要研发部管理员权限').to_response()
    d = request.get_json() or {}
    content = (d.get('content') or '').strip()
    if not content:
        return Result.fail('提醒内容不能为空').to_response()
    item = EcrReminder(
        content    = content,
        notes      = (d.get('notes') or '').strip() or None,
        created_by = (d.get('created_by') or '').strip() or None,
    )
    db.session.add(item)
    db.session.commit()
    return Result.ok(item.to_dict()).to_response()


@rd_bp.put('/reminders/<int:rid>/deactivate')
def deactivate_reminder(rid):
    """下架（软删除）指定提醒，仅 rd:admin 可用"""
    from result import Result
    from database.base import db
    from database.models.rd import EcrReminder
    if not _check_rd_admin(request):
        return Result.fail('权限不足：需要研发部管理员权限').to_response()
    item = EcrReminder.query.get(rid)
    if not item:
        return Result.fail('提醒不存在').to_response()
    item.is_active = False
    db.session.commit()
    return Result.ok(item.to_dict()).to_response()


@rd_bp.put('/reminders/<int:rid>/activate')
def activate_reminder(rid):
    """重新上架已下架提醒，仅 rd:admin 可用"""
    from result import Result
    from database.base import db
    from database.models.rd import EcrReminder
    if not _check_rd_admin(request):
        return Result.fail('权限不足：需要研发部管理员权限').to_response()
    item = EcrReminder.query.get(rid)
    if not item:
        return Result.fail('提醒不存在').to_response()
    item.is_active = True
    db.session.commit()
    return Result.ok(item.to_dict()).to_response()
