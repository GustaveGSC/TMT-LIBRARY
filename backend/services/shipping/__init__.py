import csv
import io
import os
import uuid
import openpyxl
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Dict
from database.base import db
from database.repository.shipping import ShippingTaskLeaseConflict, shipping_repository
from error_handling import report_internal_error
from result import Result

from utils import now_cst
from upload_validation import ensure_spreadsheet_row_limit

# 直辖市省名集合：这些省的 city 字段统一填写为省名本身
_MUNICIPALITY_PROVINCES = {'北京市', '天津市', '上海市', '重庆市'}
_DEFAULT_MAX_STALE_RESOLVE_ORDERS = 10_000


class StaleResolveScopeTooLarge(RuntimeError):
    pass


class ShippingRuleChangeConflict(RuntimeError):
    """A data-mutating shipping task currently owns the shared lease."""

    def __init__(self, task_id: str):
        super().__init__(task_id)
        self.task_id = task_id


def _raise_if_cancelled(cancel_check=None):
    if cancel_check and cancel_check():
        raise InterruptedError('用户已请求取消任务')


def _normalize_city(province: str, city) -> str:
    """直辖市 city 统一归一到省名（如北京市），避免出现区级名或 null"""
    if province in _MUNICIPALITY_PROVINCES:
        return province
    return city


def _max_stale_resolve_orders() -> int:
    max_orders = int(os.getenv(
        'MAX_STALE_RESOLVE_ORDERS', _DEFAULT_MAX_STALE_RESOLVE_ORDERS,
    ))
    if max_orders < 1:
        raise RuntimeError('MAX_STALE_RESOLVE_ORDERS 必须大于 0')
    return max_orders

# ── 必要列名（按列名匹配，与列顺序无关）─────────────
_REQUIRED_COL_NAMES = {
    '电商主订单号', '单据日期', '渠道名称', '渠道商', '渠道商名称',
    '最近操作人', '项次', '商品型号', '商品名称', '数量', '省份',
}

def _build_col_map(header_row, required: set = None) -> Dict[str, int]:
    """
    扫描表头行，返回 {列名: 列索引} 的映射（去除首尾空格后匹配）。
    若必要列有缺失则抛出 ValueError，列出所有缺失列名。
    required 不传时使用发货清单的必要列集合。
    """
    if required is None:
        required = _REQUIRED_COL_NAMES
    col_map = {}
    for idx, cell in enumerate(header_row):
        if cell is not None:
            col_map[str(cell).strip()] = idx

    missing = required - col_map.keys()
    if missing:
        raise ValueError(
            '文件缺少以下必要列，请确认是否上传了正确的文件：\n'
            + '、'.join(sorted(missing))
        )
    return col_map


def _str(v) -> str:
    """安全转字符串，去除首尾空格，None 返回空字符串"""
    return str(v).strip() if v is not None else ''


def _parse_shipped_date(v):
    """解析单据日期：字符串 '2024/01/11' 或 datetime 对象"""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    s = str(v).strip()
    for fmt in ('%Y/%m/%d', '%Y-%m-%d', '%Y/%m/%d %H:%M:%S'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_quantity(v):
    """解析数量，返回 Decimal 或 None"""
    if v is None:
        return None
    try:
        return Decimal(str(v).strip())
    except InvalidOperation:
        return None


def _get(row: tuple, idx: int):
    """安全取列值，超出范围返回 None"""
    return row[idx] if idx < len(row) else None


def _extract_row(row, col_map: Dict[str, int]) -> Dict:
    """按列名映射从行数据中提取所有字段"""
    def gc(name):  # get column value by name
        return _get(row, col_map[name]) if name in col_map else None

    return {
        'ecommerce_order_no': _str(gc('电商主订单号'))  or None,
        'line_no':            _str(gc('项次'))          or None,
        'shipped_date':       _parse_shipped_date(gc('单据日期')),
        'channel_name':       _str(gc('渠道名称'))      or None,
        'channel_code':       _str(gc('渠道商'))        or None,
        'channel_org_name':   _str(gc('渠道商名称'))    or None,
        'operator':           _str(gc('最近操作人'))    or None,
        'product_code':       _str(gc('商品型号'))      or None,
        'product_name':       _str(gc('商品名称'))      or None,
        'spec':               _str(gc('规格'))          or None,
        'quantity':           _parse_quantity(gc('数量')),
        'country':            _str(gc('国家'))          or None,
        'province':           _str(gc('省份'))          or None,
        'city':               _normalize_city(_str(gc('省份')) or '', _str(gc('市区')) or None),
        'district':           _str(gc('县区'))          or None,
        'street':             _str(gc('街道'))          or None,
        'address':            _str(gc('详细地址'))      or None,
        'buyer_remark':       _str(gc('买家留言'))      or None,
        'seller_remark':      _str(gc('商家备注'))      or None,
    }


def _parse_xlsx_rows(file_bytes: bytes, cancel_check=None) -> List[Dict]:
    """解析 xlsx：按列名匹配提取字段，与列顺序无关"""
    _raise_if_cancelled(cancel_check)
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    _raise_if_cancelled(cancel_check)
    ws = wb.active
    rows = []
    col_map = None
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        ensure_spreadsheet_row_limit(i)
        if i % 500 == 0:
            _raise_if_cancelled(cancel_check)
        if i == 0:
            col_map = _build_col_map(row)  # 校验必要列是否存在，返回列名→索引映射
            continue
        rows.append(_extract_row(row, col_map))
    wb.close()
    return rows


def _parse_csv_rows(file_bytes: bytes, cancel_check=None) -> List[Dict]:
    """解析 csv：按列名匹配提取字段，与列顺序无关"""
    _raise_if_cancelled(cancel_check)
    text = file_bytes.decode('utf-8-sig', errors='replace')
    _raise_if_cancelled(cancel_check)
    reader = csv.reader(io.StringIO(text))
    rows = []
    col_map = None
    for i, row in enumerate(reader):
        ensure_spreadsheet_row_limit(i)
        if i % 500 == 0:
            _raise_if_cancelled(cancel_check)
        if i == 0:
            col_map = _build_col_map(row)  # 校验必要列是否存在，返回列名→索引映射
            continue
        rows.append(_extract_row(row, col_map))
    return rows


# ── 财务端专用解析（列名：平台订单/订单单号/交易日期/部门名称/品号/数量/省/市/区）────
_REQUIRED_FINANCE_COL_NAMES = {'交易日期', '部门名称', '品号', '数量', '省'}
_FINANCE_AFTERSALE_DEPT = '售后组'


def _extract_finance_order_no(row, col_map: Dict[str, int]) -> str:
    """
    补全平台订单号：
    1. 「平台订单」不为空 → 直接使用
    2. 「平台订单」为空但「订单单号」不为空 → 取「订单单号」中第一个「-」后的部分
    3. 两者都为空 → 返回空字符串（调用方跳过该行）
    """
    platform = _str(_get(row, col_map['平台订单']) if '平台订单' in col_map else None)
    if platform:
        return platform
    order_no = _str(_get(row, col_map['订单单号']) if '订单单号' in col_map else None)
    if order_no and '-' in order_no:
        return order_no.split('-', 1)[1]
    return ''


def _extract_finance_row(row, col_map: Dict[str, int]) -> Dict:
    """按财务清单列名提取字段"""
    def gc(name):
        return _get(row, col_map[name]) if name in col_map else None

    province = _str(gc('省')) or None
    shipped_date = _parse_shipped_date(gc('交易日期'))
    return {
        'ecommerce_order_no': _extract_finance_order_no(row, col_map) or None,
        'channel_name':       _str(gc('部门名称'))  or None,
        'shipped_date':       shipped_date,
        # MySQL UNIQUE 允许多个 NULL；财务行必须使用稳定非空内部行号才能真正 UPSERT。
        'line_no':            f'F:{shipped_date:%Y%m%d}' if shipped_date else None,
        'product_code':       _str(gc('品号'))       or None,
        'product_name':       _str(gc('品名'))       or None,
        'spec':               _str(gc('规格'))       or None,
        'quantity':           _parse_quantity(gc('数量')),
        'province':           province,
        'city':               _normalize_city(province or '', _str(gc('市')) or None),
        'district':           _str(gc('区'))         or None,
        'customer_alias':     _str(gc('客户简称'))   or None,
    }


def _parse_xlsx_finance_rows(file_bytes: bytes, cancel_check=None):
    """解析财务 xlsx，返回 (shipping_rows, return_rows, aftersale_count)"""
    _raise_if_cancelled(cancel_check)
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    _raise_if_cancelled(cancel_check)
    ws = wb.active
    shipping_rows, return_rows = [], []
    aftersale_count = 0
    col_map = None
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        ensure_spreadsheet_row_limit(i)
        if i % 500 == 0:
            _raise_if_cancelled(cancel_check)
        if i == 0:
            col_map = _build_col_map(row, required=_REQUIRED_FINANCE_COL_NAMES)
            continue
        dept = _str(_get(row, col_map.get('部门名称', -1)))
        if dept == _FINANCE_AFTERSALE_DEPT:
            aftersale_count += 1
            continue
        r = _extract_finance_row(row, col_map)
        if not r.get('ecommerce_order_no') or not r.get('shipped_date'):
            continue
        qty = r.get('quantity')
        if qty is None:
            continue
        if qty > 0:
            shipping_rows.append(r)
        elif qty < 0:
            r['quantity'] = abs(qty)
            return_rows.append(r)
    wb.close()
    return shipping_rows, return_rows, aftersale_count


def _parse_csv_finance_rows(file_bytes: bytes, cancel_check=None):
    """解析财务 csv，返回 (shipping_rows, return_rows, aftersale_count)"""
    _raise_if_cancelled(cancel_check)
    text = file_bytes.decode('utf-8-sig', errors='replace')
    _raise_if_cancelled(cancel_check)
    reader = csv.reader(io.StringIO(text))
    shipping_rows, return_rows = [], []
    aftersale_count = 0
    col_map = None
    for i, row in enumerate(reader):
        ensure_spreadsheet_row_limit(i)
        if i % 500 == 0:
            _raise_if_cancelled(cancel_check)
        if i == 0:
            col_map = _build_col_map(row, required=_REQUIRED_FINANCE_COL_NAMES)
            continue
        dept = _str(_get(row, col_map.get('部门名称', -1)))
        if dept == _FINANCE_AFTERSALE_DEPT:
            aftersale_count += 1
            continue
        r = _extract_finance_row(row, col_map)
        if not r.get('ecommerce_order_no') or not r.get('shipped_date'):
            continue
        qty = r.get('quantity')
        if qty is None:
            continue
        if qty > 0:
            shipping_rows.append(r)
        elif qty < 0:
            r['quantity'] = abs(qty)
            return_rows.append(r)
    return shipping_rows, return_rows, aftersale_count


def _merge_finance_shipping_rows(rows: List[Dict]):
    """财务发货行文件内合并：按订单、品号、交易日期合并。"""
    from collections import OrderedDict
    merged: OrderedDict = OrderedDict()
    merged_away: List[Dict] = []
    for row in rows:
        key = (row.get('ecommerce_order_no'), row.get('product_code'), row.get('shipped_date'))
        if key in merged:
            existing_qty = merged[key].get('quantity') or Decimal('0')
            new_qty      = row.get('quantity') or Decimal('0')
            merged[key]['quantity'] = existing_qty + new_qty
            merged_away.append(row)
        else:
            merged[key] = dict(row)
    return list(merged.values()), merged_away


_FINANCE_SHIPPING_COMPARE_FIELDS = (
    'channel_name', 'product_name', 'spec', 'quantity',
    'province', 'city', 'district', 'customer_alias',
)
_FINANCE_RETURN_COMPARE_FIELDS = ('quantity', 'warehouse_name', 'customer_alias')


def _finance_row_changed(row: Dict, snapshot: Dict, fields) -> bool:
    """Mirror UPSERT semantics, including COALESCE for a missing customer alias."""
    for field in fields:
        incoming = row.get(field)
        existing = snapshot.get(field)
        if field == 'customer_alias' and incoming is None:
            incoming = existing
        if incoming != existing:
            return True
    return False


def _available_packaged_quantity(code, remaining, equiv_map):
    """Match existing exact-code-first availability semantics."""
    exact = remaining.get(code, 0)
    if exact > 0:
        return exact
    return sum(remaining.get(candidate, 0) for candidate in equiv_map.get(code, {code}))


def _consume_packaged_quantity(code, quantity, remaining, equiv_map):
    """Consume exact code first, then equivalent codes in lexical order."""
    left = quantity
    for candidate in sorted(
        equiv_map.get(code, {code}),
        key=lambda value: (value != code, value),
    ):
        if left <= 0:
            break
        available = remaining.get(candidate, 0)
        if available <= 0:
            continue
        take = min(available, left)
        remaining[candidate] -= take
        left -= take
        if remaining[candidate] <= 0:
            del remaining[candidate]


def _build_finished_candidate_index(sorted_finished, equiv_map):
    """
    Index each finished product by supplies that can satisfy one required anchor.

    Every valid match must satisfy its anchor, so this removes only impossible
    products. Candidate indexes are later sorted to preserve greedy order.
    """
    from collections import Counter

    requirement_frequency = Counter(
        required_code
        for _code, _name, required_codes in sorted_finished
        for required_code in required_codes
    )
    candidate_indexes = {}
    for index, (_code, _name, required_codes) in enumerate(sorted_finished):
        anchor = min(
            required_codes,
            key=lambda code: (
                requirement_frequency[code],
                len(equiv_map.get(code, {code})),
                code,
            ),
        )
        supply_codes = set(equiv_map.get(anchor, ()))
        supply_codes.add(anchor)
        for supply_code in supply_codes:
            candidate_indexes.setdefault(supply_code, set()).add(index)
    return candidate_indexes


def _build_sorted_finished_rules(finished_list):
    """Build stable resolver rules: complex products first, then code ascending."""
    finished_rules = []
    for finished in finished_list:
        required_codes = tuple(sorted(
            packaged.code for packaged in finished.packaged_list
        ))
        if required_codes:
            finished_rules.append((
                finished.code,
                _get_finished_name(finished),
                required_codes,
            ))
    return sorted(
        finished_rules,
        key=lambda item: (-len(item[2]), item[0]),
    )


def _get_finished_candidates(remaining, sorted_finished, candidate_index=None):
    if candidate_index is None:
        return sorted_finished
    indexes = set()
    for supply_code, quantity in remaining.items():
        if quantity > 0:
            indexes.update(candidate_index.get(supply_code, ()))
    return [sorted_finished[index] for index in sorted(indexes)]


def _greedy_match_finished(product_quantities, sorted_finished, equiv_map,
                           candidate_index=None):
    """Return ({finished_code: qty}, remaining products) with legacy semantics."""
    remaining = dict(product_quantities)
    matched = {}
    candidates = _get_finished_candidates(
        remaining, sorted_finished, candidate_index,
    )
    for finished_code, _finished_name, required_codes in candidates:
        if not all(
            _available_packaged_quantity(code, remaining, equiv_map) > 0
            for code in required_codes
        ):
            continue
        quantity = min(
            _available_packaged_quantity(code, remaining, equiv_map)
            for code in required_codes
        )
        if quantity <= 0:
            continue
        for code in required_codes:
            _consume_packaged_quantity(code, quantity, remaining, equiv_map)
        matched[finished_code] = matched.get(finished_code, 0) + quantity
    return matched, remaining


def _serialize_finance_skipped_row(r: Dict) -> Dict:
    """财务导入跳过行序列化"""
    shipped = r.get('shipped_date')
    qty = r.get('quantity')
    return {
        'ecommerce_order_no': r.get('ecommerce_order_no'),
        'product_code':       r.get('product_code'),
        'shipped_date':       shipped.strftime('%Y-%m-%d') if shipped else None,
        'quantity':           float(qty) if qty is not None else None,
    }


def _serialize_row(r: Dict) -> Dict:
    """将内存中的原始行转为可 JSON 序列化的 dict（全列）"""
    qty     = r.get('quantity')
    shipped = r.get('shipped_date')
    return {
        'ecommerce_order_no': r.get('ecommerce_order_no'),
        'line_no':            r.get('line_no'),
        'shipped_date':       shipped.strftime('%Y-%m-%d') if shipped else None,
        'channel_name':       r.get('channel_name'),
        'channel_code':       r.get('channel_code'),
        'channel_org_name':   r.get('channel_org_name'),
        'operator':           r.get('operator'),
        'product_code':       r.get('product_code'),
        'product_name':       r.get('product_name'),
        'spec':               r.get('spec'),
        'quantity':           float(qty) if qty is not None else None,
        'country':            r.get('country'),
        'province':           r.get('province'),
        'city':               r.get('city'),
        'district':           r.get('district'),
        'street':             r.get('street'),
        'address':            r.get('address'),
        'buyer_remark':       r.get('buyer_remark'),
        'seller_remark':      r.get('seller_remark'),
    }


def _merge_rows(rows: List[Dict]):
    """
    将文件内相同 (ecommerce_order_no, line_no, product_code) 的行合并：
    - 数量（quantity）累加，其余字段取首行的值
    - 返回 (merged_rows, merged_away_rows)
    """
    from collections import OrderedDict
    merged:      OrderedDict = OrderedDict()
    merged_away: List[Dict]  = []
    for row in rows:
        key = (row.get('ecommerce_order_no'), row.get('line_no'), row.get('product_code'))
        if key in merged:
            existing_qty = merged[key].get('quantity') or Decimal('0')
            new_qty      = row.get('quantity') or Decimal('0')
            merged[key]['quantity'] = existing_qty + new_qty
            merged_away.append(row)   # 记录被合并掉的原始行
        else:
            merged[key] = dict(row)
    return list(merged.values()), merged_away


def _merge_return_rows(rows: List[Dict]):
    """
    将文件内相同 (ecommerce_order_no, product_code, shipped_date) 的销退行合并：
    - 数量（quantity）累加，warehouse_name 取首行的值
    - 返回 (merged_rows, merged_away_rows)
    """
    from collections import OrderedDict
    merged:      OrderedDict = OrderedDict()
    merged_away: List[Dict]  = []
    for row in rows:
        key = (row.get('ecommerce_order_no'), row.get('product_code'), row.get('shipped_date'))
        if key in merged:
            existing_qty = merged[key].get('quantity') or Decimal('0')
            new_qty      = row.get('quantity') or Decimal('0')
            merged[key]['quantity'] = existing_qty + new_qty
            merged_away.append(row)
        else:
            merged[key] = dict(row)
    return list(merged.values()), merged_away


def _load_resolver_context(cancel_check=None):
    """Load immutable product/equivalent rules once for a staged task."""
    from database.models.product.finished import ProductFinished, PackagedEquivalent
    from sqlalchemy.orm import selectinload
    from collections import defaultdict

    finished_list = ProductFinished.query.options(
        selectinload(ProductFinished.packaged_list)
    ).all()
    _raise_if_cancelled(cancel_check)
    sorted_finished = _build_sorted_finished_rules(finished_list)
    equiv_map: Dict = defaultdict(set)
    for equivalent in PackagedEquivalent.query.all():
        equiv_map[equivalent.code_a].update([
            equivalent.code_a, equivalent.code_b,
        ])
        equiv_map[equivalent.code_b].update([
            equivalent.code_a, equivalent.code_b,
        ])
    return {
        'sorted_finished': sorted_finished,
        'equiv_map': equiv_map,
        'candidate_index': _build_finished_candidate_index(
            sorted_finished, equiv_map,
        ),
        'finished_name_by_code': {
            finished_code: finished_name
            for finished_code, finished_name, _required in sorted_finished
        },
    }


def _resolve_orders(order_nos: List[str], source: str = 'shipping', progress_cb=None,
                    commit_chunks: bool = True, cancel_check=None,
                    resolver_context=None, staging_task_id=None,
                    generation_task_id=None):
    """
    对给定订单号列表，执行成品组合匹配，写入 shipping_order_finished。
    source: 'shipping' 或 'finance'，决定从哪个来源的 shipping_record 读取产成品数据。
    匹配逻辑：
      1. 取订单内所有产成品编码及数量
      2. 遍历产品库中所有成品，找出成品的产成品集合是订单产成品集合的子集
      3. 贪心匹配：优先匹配产成品数最多的成品，按最小分量计算成品数量
    """
    _raise_if_cancelled(cancel_check)
    if not order_nos:
        return

    total_orders = len(order_nos)

    if progress_cb and resolver_context is None:
        progress_cb('preparing', message='正在加载产品库…', total=total_orders)
    context = resolver_context or _load_resolver_context(cancel_check)
    sorted_finished = context['sorted_finished']
    equiv_map = context['equiv_map']
    candidate_index = context['candidate_index']
    finished_name_by_code = context['finished_name_by_code']

    # 分批加载发货数据，每批推送一次进度
    CHUNK = 2000
    order_data: Dict = {}
    for i in range(0, total_orders, CHUNK):
        _raise_if_cancelled(cancel_check)
        chunk = order_nos[i:i + CHUNK]
        order_data.update(shipping_repository.get_order_products(chunk, source=source))
        _raise_if_cancelled(cancel_check)
        if progress_cb:
            progress_cb('preparing', message='正在加载发货数据…',
                        current=min(i + CHUNK, total_orders), total=total_orders)

    # 分批加载销退数据
    return_data: Dict = {}
    for i in range(0, total_orders, CHUNK):
        _raise_if_cancelled(cancel_check)
        chunk = order_nos[i:i + CHUNK]
        return_data.update(shipping_repository.get_order_return_products(chunk))
        _raise_if_cancelled(cancel_check)
        if progress_cb:
            progress_cb('preparing', message='正在加载销退数据…',
                        current=min(i + CHUNK, total_orders), total=total_orders)

    # 对每个订单预先跑一次贪心匹配，得到 {order_no: {finished_code: return_qty}}
    return_resolved: Dict[str, Dict] = {}
    for idx, (order_no, return_products) in enumerate(return_data.items()):
        if idx % 100 == 0:
            _raise_if_cancelled(cancel_check)
        order_ret, _remaining_ret = _greedy_match_finished(
            return_products, sorted_finished, equiv_map, candidate_index,
        )
        return_resolved[order_no] = order_ret

    if staging_task_id is None and generation_task_id is None:
        # 导入增量路径仍在自己的原子业务事务中直接替换正式结果。
        _raise_if_cancelled(cancel_check)
        shipping_repository.delete_order_finished(
            order_nos, source=source, commit_chunks=commit_chunks,
            cancel_check=cancel_check,
        )

    resolved_at = now_cst()
    to_insert = []
    total_orders = len(order_data)

    for idx, (order_no, data) in enumerate(order_data.items()):
        if idx % 100 == 0:
            _raise_if_cancelled(cancel_check)
        # 每处理 100 个订单推送一次进度
        if progress_cb and idx % 100 == 0:
            progress_cb('resolving', current=idx, total=total_orders)
        matched_finished, remaining = _greedy_match_finished(
            data['product_codes'], sorted_finished, equiv_map, candidate_index,
        )
        meta = data['meta']
        order_ret = return_resolved.get(order_no, {})

        for f_code, matched_quantity in matched_finished.items():
            rq = Decimal(str(order_ret.get(f_code, 0)))
            sq = Decimal(str(matched_quantity))
            to_insert.append({
                'ecommerce_order_no': order_no,
                'finished_code':      f_code,
                'finished_name':      finished_name_by_code[f_code],
                'quantity':           sq,
                'return_quantity':    rq,
                'actual_quantity':    sq - rq,
                'shipped_date':       meta['shipped_date'],
                'operator':           meta['operator'],
                'channel_name':       meta['channel_name'],
                'channel_code':       meta.get('channel_code'),
                'channel_org_name':   meta.get('channel_org_name'),
                'province':           meta['province'],
                'city':               _normalize_city(meta['province'], meta.get('city')),
                'district':           meta.get('district'),
                'customer_alias':     meta.get('customer_alias'),
                'source':             source,
                'resolved_at':        resolved_at,
            })

        # 剩余未匹配的产成品：写一行 finished_code=None 的记录，方便追踪
        for code, qty in remaining.items():
            if qty > 0:
                sq = Decimal(str(qty))
                to_insert.append({
                    'ecommerce_order_no': order_no,
                    'finished_code':      None,
                    'finished_name':      None,
                    'quantity':           sq,
                    'return_quantity':    Decimal('0'),
                    'actual_quantity':    sq,
                    'shipped_date':       meta['shipped_date'],
                    'operator':           meta['operator'],
                    'channel_name':       meta['channel_name'],
                    'channel_code':       meta.get('channel_code'),
                    'channel_org_name':   meta.get('channel_org_name'),
                    'province':           meta['province'],
                    'city':               _normalize_city(meta['province'], meta.get('city')),
                    'district':           meta.get('district'),
                    'customer_alias':     meta.get('customer_alias'),
                    'source':             source,
                    'resolved_at':        resolved_at,
                })

    if progress_cb:
        progress_cb('resolving', current=total_orders, total=total_orders)

    _raise_if_cancelled(cancel_check)
    if generation_task_id is not None:
        expected_orders = set(order_nos)
        if any(
            row.get('source') != source
            or row.get('ecommerce_order_no') not in expected_orders
            for row in to_insert
        ):
            raise RuntimeError('全量重算结果越出当前订单分块范围')
        shipping_repository.bulk_insert_order_finished_generation(
            generation_task_id,
            to_insert,
            progress_cb=progress_cb,
            cancel_check=cancel_check,
        )
    elif staging_task_id is None:
        shipping_repository.bulk_insert_order_finished(
            to_insert, progress_cb=progress_cb, commit_chunks=commit_chunks,
            cancel_check=cancel_check,
        )
    else:
        shipping_repository.bulk_insert_order_finished_staging(
            staging_task_id,
            to_insert,
            progress_cb=progress_cb,
            cancel_check=cancel_check,
        )


def _get_finished_name(finished) -> str:
    """取成品显示名称：优先用中文名，无则用编码"""
    if finished.model and finished.model.name:
        return finished.model.name
    return finished.code


class ShippingService:
    def _run_rule_change(self, task_label: str, mutation) -> Dict:
        """Serialize rule writes with imports/resolves and atomically mark stale.

        The short-lived task uses the same DB-backed lease as every shipping
        data mutation.  `mutation` must only flush ORM changes; this method
        owns the single commit so a changed rule can never be visible without
        its corresponding stale markers.
        """
        task_id = str(uuid.uuid4())
        try:
            shipping_repository.create_task(
                task_id, 'rule_change', task_label,
                lease_key='shipping_data_mutation',
            )
        except ShippingTaskLeaseConflict as exc:
            raise ShippingRuleChangeConflict(exc.task_id) from exc
        try:
            result = mutation()
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            shipping_repository.update_task(task_id, status='error', message=str(exc))
            raise
        shipping_repository.update_task(task_id, status='done', result=result)
        return result

    @staticmethod
    def _scope_result(stale_pairs: int) -> Dict:
        stale_limit = _max_stale_resolve_orders()
        return {
            'stale_pairs': stale_pairs,
            'stale_limit': stale_limit,
            'requires_full_resolve': stale_pairs > stale_limit,
        }

    @staticmethod
    def _direct_equivalent_codes(component_codes: set) -> set:
        """Expand one direct equivalent edge, matching resolver semantics exactly."""
        if not component_codes:
            return set()
        from database.models.product.finished import PackagedEquivalent
        rows = PackagedEquivalent.query.filter(
            db.or_(
                PackagedEquivalent.code_a.in_(component_codes),
                PackagedEquivalent.code_b.in_(component_codes),
            )
        ).all()
        expanded = set(component_codes)
        for row in rows:
            expanded.update((row.code_a, row.code_b))
        return expanded

    def save_finished_packaged_relation(self, finished_id: int, packaged_id: int, *, add: bool) -> Dict:
        """Change a finished/component edge and mark only its affected orders stale."""
        def mutation():
            from database.models.product.finished import ProductFinished, ProductPackaged
            finished = db.session.get(ProductFinished, finished_id)
            packaged = db.session.get(ProductPackaged, packaged_id)
            if not finished:
                raise ValueError('成品不存在')
            if not packaged:
                raise ValueError('产成品不存在')
            exists = packaged in finished.packaged_list
            if exists == add:
                return {'changed': False, **self._scope_result(0)}
            before_codes = {item.code for item in finished.packaged_list}
            after_codes = set(before_codes)
            if add:
                after_codes.add(packaged.code)
            else:
                after_codes.discard(packaged.code)
            affected_components = self._direct_equivalent_codes(before_codes | after_codes)
            if add:
                finished.packaged_list.append(packaged)
            else:
                finished.packaged_list.remove(packaged)
            db.session.flush()
            stale_pairs = shipping_repository.mark_stale_for_component_codes(
                affected_components, {finished.code},
            )
            return {'changed': True, **self._scope_result(stale_pairs)}

        return self._run_rule_change('finished_packaged_relation', mutation)

    def add_equivalent(self, code_a: str, code_b: str, note=None) -> Dict:
        from database.models.product.finished import PackagedEquivalent, ProductPackaged

        if not code_a or not code_b:
            raise ValueError('code_a 和 code_b 不能为空')
        if code_a == code_b:
            raise ValueError('两个产成品编码不能相同')
        if code_a > code_b:
            code_a, code_b = code_b, code_a
        def mutation():
            existing_codes = {row.code for row in ProductPackaged.query.filter(
                ProductPackaged.code.in_([code_a, code_b]),
            ).all()}
            missing = [code for code in (code_a, code_b) if code not in existing_codes]
            if missing:
                raise ValueError(f'产成品编码不存在：{", ".join(missing)}')
            if PackagedEquivalent.query.filter_by(code_a=code_a, code_b=code_b).first():
                raise ValueError('该通用件对已存在')
            from utils import now_cst
            pair = PackagedEquivalent(
                code_a=code_a, code_b=code_b, note=note, created_at=now_cst(),
            )
            db.session.add(pair)
            db.session.flush()
            stale_pairs = shipping_repository.mark_stale_for_component_codes(
                {code_a, code_b}, set(),
            )
            names = {row.code: row.name for row in ProductPackaged.query.filter(
                ProductPackaged.code.in_([code_a, code_b]),
            ).all()}
            data = pair.to_dict()
            data.update({
                'name_a': names.get(code_a, ''),
                'name_b': names.get(code_b, ''),
            })
            return {**data, **self._scope_result(stale_pairs)}

        return self._run_rule_change('packaged_equivalent_add', mutation)

    def delete_equivalent(self, eq_id: int) -> Dict:
        from database.models.product.finished import PackagedEquivalent
        def mutation():
            pair = db.session.get(PackagedEquivalent, eq_id)
            if not pair:
                raise ValueError('记录不存在')
            codes = {pair.code_a, pair.code_b}
            db.session.delete(pair)
            db.session.flush()
            stale_pairs = shipping_repository.mark_stale_for_component_codes(codes, set())
            return self._scope_result(stale_pairs)

        return self._run_rule_change('packaged_equivalent_delete', mutation)


    def import_shipping(self, filename: str, file_bytes: bytes,
                        progress_cb=None, cancel_check=None,
                        begin_commit=None) -> Dict:
        """导入发货清单：文件内合并 → 与库去重 → 插入新行 → 成品组合"""
        def notify(step, **kwargs):
            if progress_cb:
                progress_cb(step, **kwargs)

        batch = None
        try:
            _raise_if_cancelled(cancel_check)
            notify('parsing')
            name_lower = filename.lower()
            rows = (
                _parse_csv_rows(file_bytes, cancel_check=cancel_check)
                if name_lower.endswith('.csv')
                else _parse_xlsx_rows(file_bytes, cancel_check=cancel_check)
            )

            total = len(rows)
            rows, merged_away_rows = _merge_rows(rows)   # 文件内相同 key 合并
            _raise_if_cancelled(cancel_check)

            # 与数据库比对，分出新行和跳过行
            keys          = [(r.get('ecommerce_order_no'), r.get('line_no'), r.get('product_code')) for r in rows]
            existing_keys = shipping_repository.get_existing_keys(
                keys, record_type='shipping', cancel_check=cancel_check,
            )
            new_rows      = [r for r in rows if (r.get('ecommerce_order_no'), r.get('line_no'), r.get('product_code')) not in existing_keys]
            skipped_rows  = [r for r in rows if (r.get('ecommerce_order_no'), r.get('line_no'), r.get('product_code')) in existing_keys]
            notify('parsed', total=total)

            imported_at = now_cst()
            notify('inserting', current=0, total=len(new_rows))
            batch = shipping_repository.create_batch('shipping', filename, total, imported_at)

            def on_insert_progress(current, total_rows):
                if cancel_check and cancel_check():
                    raise InterruptedError('用户已中止导入')
                notify('inserting', current=current, total=total_rows)

            inserted = shipping_repository.bulk_insert_shipping(batch.id, new_rows, progress_cb=on_insert_progress,
                                                                    record_type='shipping', commit_chunks=False,
                                                                    cancel_check=cancel_check)
            notify('inserted', inserted=inserted, skipped=len(skipped_rows))

            # 对本批次新增的订单触发成品组合
            new_order_nos = shipping_repository.get_new_order_nos_by_source(batch.id, source='shipping')
            if new_order_nos:
                notify('resolving', current=0, total=len(new_order_nos))
                _resolve_orders(
                    new_order_nos, source='shipping', progress_cb=progress_cb,
                    commit_chunks=False,
                    cancel_check=cancel_check,
                )

            _raise_if_cancelled(cancel_check)
            if begin_commit and not begin_commit():
                raise InterruptedError('取消请求先于最终提交生效')
            db.session.commit()

            return {
                'total':             total,
                'merged_away':       len(merged_away_rows),
                'inserted':          inserted,
                'skipped':           len(skipped_rows),
                'skipped_rows':      [_serialize_row(r) for r in skipped_rows],
                'merged_away_rows':  [_serialize_row(r) for r in merged_away_rows],
            }
        except Exception:
            db.session.rollback()
            raise

    def import_finance(self, filename: str, file_bytes: bytes,
                       progress_cb=None, cancel_check=None,
                       begin_commit=None) -> Dict:
        """导入财务清单：过滤售后组 → 拆分发货/销退 → 文件内合并 → 与库去重 → 插入 → 成品组合"""
        def notify(step, **kwargs):
            if progress_cb:
                progress_cb(step, **kwargs)

        batch = None
        try:
            _raise_if_cancelled(cancel_check)
            notify('parsing')
            name_lower = filename.lower()
            if name_lower.endswith('.csv'):
                shipping_rows, return_rows, aftersale_count = _parse_csv_finance_rows(
                    file_bytes, cancel_check=cancel_check,
                )
            else:
                shipping_rows, return_rows, aftersale_count = _parse_xlsx_finance_rows(
                    file_bytes, cancel_check=cancel_check,
                )

            total = len(shipping_rows) + len(return_rows) + aftersale_count

            # 文件内合并
            shipping_rows, shipping_merged_away = _merge_finance_shipping_rows(shipping_rows)
            return_rows,   return_merged_away   = _merge_return_rows(return_rows)
            _raise_if_cancelled(cancel_check)

            # DB 去重：发货行按 (order_no, product_code, date, source='finance')
            s_keys          = [(r.get('ecommerce_order_no'), r.get('product_code'), r.get('shipped_date')) for r in shipping_rows]
            shipping_snapshots = shipping_repository.get_finance_shipping_snapshots(
                s_keys, cancel_check=cancel_check,
            )
            new_shipping = []
            changed_shipping = []
            unchanged_shipping = []
            for row in shipping_rows:
                key = (
                    row.get('ecommerce_order_no'),
                    row.get('product_code'),
                    row.get('shipped_date'),
                )
                snapshot = shipping_snapshots.get(key)
                if snapshot is None:
                    new_shipping.append(row)
                elif _finance_row_changed(
                    row, snapshot, _FINANCE_SHIPPING_COMPARE_FIELDS,
                ):
                    changed_shipping.append(row)
                else:
                    unchanged_shipping.append(row)

            # DB 去重：销退行（复用 return_record 去重）
            r_keys          = [(r.get('ecommerce_order_no'), r.get('product_code'), r.get('shipped_date')) for r in return_rows]
            return_snapshots = shipping_repository.get_finance_return_snapshots(
                r_keys, cancel_check=cancel_check,
            )
            new_returns = []
            changed_returns = []
            unchanged_returns = []
            for row in return_rows:
                key = (
                    row.get('ecommerce_order_no'),
                    row.get('product_code'),
                    row.get('shipped_date'),
                )
                snapshot = return_snapshots.get(key)
                if snapshot is None:
                    new_returns.append(row)
                elif _finance_row_changed(
                    row, snapshot, _FINANCE_RETURN_COMPARE_FIELDS,
                ):
                    changed_returns.append(row)
                else:
                    unchanged_returns.append(row)

            notify('parsed', total=total)

            imported_at = now_cst()
            notify('inserting', current=0, total=len(new_shipping) + len(new_returns))
            batch = shipping_repository.create_batch('finance', filename, total, imported_at)

            def on_insert_progress(current, total_rows):
                if cancel_check and cancel_check():
                    raise InterruptedError('用户已中止导入')
                notify('inserting', current=current, total=total_rows)

            shipping_to_write = new_shipping + changed_shipping
            returns_to_write = new_returns + changed_returns
            shipping_repository.bulk_insert_shipping(
                batch.id, shipping_to_write,
                progress_cb=on_insert_progress,
                record_type='shipping', source='finance', commit_chunks=False,
                cancel_check=cancel_check,
            )
            shipping_repository.bulk_insert_return(
                batch.id, returns_to_write,
                progress_cb=on_insert_progress,
                commit_chunks=False,
                cancel_check=cancel_check,
            )
            imported_shipping_order_nos = sorted({
                row.get('ecommerce_order_no')
                for row in shipping_rows
                if row.get('ecommerce_order_no')
            })
            (
                customer_alias_conflicts_count,
                customer_alias_conflicts_order_nos,
            ) = shipping_repository.get_finance_customer_alias_conflicts(
                imported_shipping_order_nos,
                limit=100,
                cancel_check=cancel_check,
            )
            notify('inserted',
                   inserted=len(new_shipping),
                   updated=len(changed_shipping),
                   inserted_returns=len(new_returns),
                   updated_returns=len(changed_returns),
                   skipped=len(unchanged_shipping),
                   aftersale_filtered=aftersale_count)

            # 新增或实际变化的发货/销退都会影响派生组合；完全相同行不写库也不重算。
            affected_order_nos = sorted({
                row.get('ecommerce_order_no')
                for row in shipping_to_write + returns_to_write
                if row.get('ecommerce_order_no')
            })
            if affected_order_nos:
                notify('resolving', current=0, total=len(affected_order_nos))
                _resolve_orders(
                    affected_order_nos, source='finance', progress_cb=progress_cb,
                    commit_chunks=False,
                    cancel_check=cancel_check,
                )

            _raise_if_cancelled(cancel_check)
            if begin_commit and not begin_commit():
                raise InterruptedError('取消请求先于最终提交生效')
            db.session.commit()

            return {
                'total':              total,
                'aftersale_filtered': aftersale_count,
                'inserted':           len(new_shipping),
                'updated':            len(changed_shipping),
                'inserted_returns':   len(new_returns),
                'updated_returns':    len(changed_returns),
                'skipped':            len(unchanged_shipping),
                'skipped_returns':    len(unchanged_returns),
                'customer_alias_conflicts_count': customer_alias_conflicts_count,
                'customer_alias_conflicts_order_nos': customer_alias_conflicts_order_nos,
                'customer_alias_conflicts_truncated': (
                    customer_alias_conflicts_count
                    > len(customer_alias_conflicts_order_nos)
                ),
                'skipped_rows':       [
                    _serialize_finance_skipped_row(r)
                    for r in unchanged_shipping
                ],
            }
        except Exception:
            db.session.rollback()
            raise

    def get_operators(self) -> List[Dict]:
        return shipping_repository.get_all_operators()

    def classify_operators(self, items: List[Dict]) -> Dict:
        count = shipping_repository.classify_operators(items)
        return {'updated': count}

    def _run_staged_resolve(self, task_id: str, pairs, *, full_rebuild: bool,
                            progress_cb=None, cancel_check=None,
                            begin_commit=None) -> Dict:
        """Build a committed private generation, then atomically cut it over."""
        from collections import defaultdict

        unique_pairs = sorted({
            (order_no, source)
            for order_no, source in pairs
            if order_no and source in ('shipping', 'finance')
        }, key=lambda pair: (pair[1], pair[0]))
        try:
            shipping_repository.cleanup_abandoned_resolve_staging()
            shipping_repository.cleanup_resolve_staging(task_id)
            if full_rebuild:
                shipping_repository.reset_full_resolve_generation(task_id)
            target_count = shipping_repository.create_resolve_targets(
                task_id, unique_pairs, cancel_check=cancel_check,
            )
            _raise_if_cancelled(cancel_check)
            context = _load_resolver_context(cancel_check)
            by_source = defaultdict(list)
            for order_no, source in unique_pairs:
                by_source[source].append(order_no)

            processed = 0
            chunk_size = 2000
            for source in ('shipping', 'finance'):
                order_nos = by_source.get(source, [])
                for index in range(0, len(order_nos), chunk_size):
                    _raise_if_cancelled(cancel_check)
                    chunk = order_nos[index:index + chunk_size]
                    _resolve_orders(
                        chunk,
                        source=source,
                        progress_cb=None,
                        cancel_check=cancel_check,
                        resolver_context=context,
                        staging_task_id=(
                            None if full_rebuild else task_id
                        ),
                        generation_task_id=(
                            task_id if full_rebuild else None
                        ),
                    )
                    processed += len(chunk)
                    if progress_cb:
                        progress_cb(
                            'resolving',
                            current=processed,
                            total=target_count,
                        )

            stats = (
                shipping_repository.get_full_generation_stats(task_id)
                if full_rebuild
                else shipping_repository.get_resolve_staging_stats(task_id)
            )
            if stats['target_count'] != target_count:
                raise RuntimeError('重算目标数量校验失败')
            if stats['orphan_count'] != 0:
                raise RuntimeError('重算暂存结果存在范围外订单')
            _raise_if_cancelled(cancel_check)
            if begin_commit and not begin_commit():
                raise InterruptedError('取消请求先于最终切换生效')

            # Drop the ORM transaction/connection before the short engine-level cutover.
            db.session.remove()
            cutover = (
                shipping_repository.publish_full_generation(
                    task_id,
                    resolved_count=target_count,
                    generation_rows=stats['staging_count'],
                )
                if full_rebuild
                else shipping_repository.cutover_resolve_staging(
                    task_id,
                    full_rebuild=False,
                    resolved_count=target_count,
                    staged_rows=stats['staging_count'],
                )
            )
            try:
                shipping_repository.cleanup_resolve_staging(task_id)
                cleanup_pending = False
            except Exception:
                cleanup_pending = True
                report_internal_error(
                    context=f'清理重算暂存数据失败 task_id={task_id}',
                )
            if cleanup_pending:
                cutover['cleanup_pending'] = True
                try:
                    shipping_repository.update_task(
                        task_id,
                        result=cutover,
                        progress={'step': 'done', 'data': cutover},
                    )
                except Exception:
                    # The live cutover and terminal task state are already
                    # committed. A diagnostic update must never turn that
                    # successful publication into a reported task failure.
                    report_internal_error(
                        context=f'更新重算暂存清理状态失败 task_id={task_id}',
                    )
            return cutover
        except Exception:
            db.session.rollback()
            try:
                shipping_repository.cleanup_resolve_staging(task_id)
            except Exception:
                report_internal_error(
                    context=f'异常后清理重算暂存数据失败 task_id={task_id}',
                )
            raise

    def resolve_stale(self, task_id: str, progress_cb=None,
                      cancel_check=None, begin_commit=None) -> Dict:
        """Safely rebuild stale orders through task-isolated staging."""
        stale_pairs = shipping_repository.get_stale_order_nos()
        max_orders = _max_stale_resolve_orders()
        if len(stale_pairs) > max_orders:
            raise StaleResolveScopeTooLarge(
                f'待重算订单 {len(stale_pairs)} 条，超过当前安全上限 '
                f'{max_orders} 条；请先完成大规模旧数据重算门禁'
            )
        return self._run_staged_resolve(
            task_id,
            stale_pairs,
            full_rebuild=False,
            progress_cb=progress_cb,
            cancel_check=cancel_check,
            begin_commit=begin_commit,
        )

    def get_stats(self) -> Dict:
        return shipping_repository.get_stats()

    def resolve_all(self, task_id: str, progress_cb=None,
                    cancel_check=None, begin_commit=None) -> Dict:
        """Safely rebuild both sources and cut over one complete generation."""
        shipping_nos = shipping_repository.get_all_order_nos_by_source('shipping')
        finance_nos  = shipping_repository.get_all_order_nos_by_source('finance')
        pairs = (
            [(order_no, 'shipping') for order_no in shipping_nos]
            + [(order_no, 'finance') for order_no in finance_nos]
        )
        return self._run_staged_resolve(
            task_id,
            pairs,
            full_rebuild=True,
            progress_cb=progress_cb,
            cancel_check=cancel_check,
            begin_commit=begin_commit,
        )

    def get_shipped_dates(self) -> List[str]:
        return shipping_repository.get_distinct_shipped_dates()

    def get_warehouses(self) -> List[Dict]:
        return shipping_repository.get_all_warehouses()

    def save_warehouse_filters(self, items: List[Dict]) -> Dict:
        normalized = {
            (item.get('warehouse_name') or '').strip(): bool(item.get('is_excluded', False))
            for item in items
            if (item.get('warehouse_name') or '').strip()
        }
        def mutation():
            before = shipping_repository.get_warehouse_filter_states(set(normalized))
            changed_names = {
                name for name, excluded in normalized.items()
                if before.get(name, False) != excluded
            }
            count = shipping_repository.save_warehouse_filters(items)
            db.session.flush()
            stale_pairs = shipping_repository.mark_stale_for_warehouse_names(changed_names)
            return {'updated': count, **self._scope_result(stale_pairs)}

        return self._run_rule_change('warehouse_filter_save', mutation)

    def get_finance_customer_aliases(self, keyword=None, status=None, page=1, per_page=100) -> Dict:
        return shipping_repository.get_finance_customer_aliases(
            keyword=keyword, status=status, page=page, per_page=per_page,
        )

    def save_finance_customer_mapping(self, payload: Dict) -> Dict:
        customer_alias = _str(payload.get('customer_alias'))
        if not customer_alias:
            raise ValueError('customer_alias 不能为空')
        if len(customer_alias) > 255:
            raise ValueError('customer_alias 不能超过 255 个字符')
        status = payload.get('status')
        valid_statuses = {'pending', 'export', 'domestic', 'non_sales'}
        if status not in valid_statuses:
            raise ValueError('status 必须是 pending、export、domestic、non_sales 之一')

        def optional_text(name, max_length):
            value = _str(payload.get(name)) or None
            if value and len(value) > max_length:
                raise ValueError(f'{name} 不能超过 {max_length} 个字符')
            return value

        return shipping_repository.save_finance_customer_mapping(
            customer_alias=customer_alias,
            status=status,
            country=optional_text('country', 100),
            brand=optional_text('brand', 100),
            note=optional_text('note', 1000),
        )

    def get_chart_options(self, date_start=None, date_end=None, source: str = 'shipping') -> Dict:
        return shipping_repository.get_chart_options(date_start=date_start, date_end=date_end, source=source)

    def get_chart_data(self, params: Dict) -> Dict:
        return shipping_repository.get_chart_data(params)

    def get_product_monthly(self, code: str, source: str = 'shipping') -> Result:
        data = shipping_repository.get_product_monthly(code, source=source)
        return Result.ok(data)

    def get_orders(self, page: int, size: int, filters: Dict, sort_field: str, sort_order: str) -> Dict:
        return shipping_repository.get_orders(page, size, filters, sort_field, sort_order)


shipping_service = ShippingService()
