from datetime import datetime, timezone, timedelta
from database.base import db
from database.models.product.finished import ProductFinished
from database.models.shipping import ShippingOrderFinished, ShippingOperatorType
from sqlalchemy import func


# ── 时区 ──────────────────────────────────────────────────────────────────────
_CST = timezone(timedelta(hours=8))


def _now_cst():
    return datetime.now(_CST).replace(tzinfo=None)


# ── 月份字符串辅助函数（格式 'YYYY-MM'）────────────────────────────────────────

def _prev_month(ym: str) -> str:
    """返回 ym 的上一个月，例如 '2024-01' → '2023-12'"""
    y, m = int(ym[:4]), int(ym[5:])
    if m == 1:
        return f'{y - 1}-12'
    return f'{y}-{m - 1:02d}'


def _next_month(ym: str) -> str:
    """返回 ym 的下一个月，例如 '2023-12' → '2024-01'"""
    y, m = int(ym[:4]), int(ym[5:])
    if m == 12:
        return f'{y + 1}-01'
    return f'{y}-{m + 1:02d}'


def _subtract_months(ym: str, n: int) -> str:
    """将 ym 往前推 n 个月"""
    y, m = int(ym[:4]), int(ym[5:])
    m -= n
    while m <= 0:
        m += 12
        y -= 1
    return f'{y}-{m:02d}'


def _month_diff(ym_a: str, ym_b: str) -> int:
    """返回 ym_a - ym_b 的月份差（可为负）"""
    ay, am = int(ym_a[:4]), int(ym_a[5:])
    by, bm = int(ym_b[:4]), int(ym_b[5:])
    return (ay - by) * 12 + (am - bm)


def _effective_last_month(
    sorted_months: list,
    gap_threshold: int = 3,
    qty_by_month: dict = None,
    relaunch_ratio: float = 0.5,
) -> str:
    """
    从已排序的发货月份列表中，找出最后一个「连续活跃块」的末尾月份。

    算法：先找到最后一个连续块（向左扩展直到遇到间隔 >= gap_threshold 或到达头部），
    判断该连续块与前面主体之间的断开间隔是否 >= gap_threshold：
    - 若间隔不够大：整体是一个连续块，直接返回最后一个月。
    - 若间隔够大（孤立尾部）：
        - 若提供了 qty_by_month，计算尾部块月均销量；
          若尾部月均销量 >= 主体历史月均销量 * relaunch_ratio，
          视为重新上市，返回尾部块末尾（即最后一个月）。
        - 否则视为孤立尾部，递归处理剩余部分（支持多层孤立尾部）。

    例：['2024-06','2024-07','2024-08','2025-08']
        → '2025-08' 孤立且销量小 → 返回 '2024-08'

    例：['2024-06','2024-07','2024-08','2025-08']，2025-08 销量 >> 历史均值
        → 视为重新上市 → 返回 '2025-08'

    例：['2024-06','2024-07','2024-08','2025-05','2025-06']，尾部销量小
        → 尾部连续块孤立 → 返回 '2024-08'
    """
    if not sorted_months:
        return None

    n = len(sorted_months)
    if n == 1:
        return sorted_months[-1]

    # 找到最后一个连续块的起始索引（从右向左，直到遇到大间隔或到达列表头）
    tail_start = n - 1
    while tail_start > 0:
        diff = _month_diff(sorted_months[tail_start], sorted_months[tail_start - 1])
        if diff >= gap_threshold:
            break
        tail_start -= 1

    if tail_start == 0:
        # 整个列表是一个连续块，末尾即为最后一个月
        return sorted_months[-1]

    # 尾部连续块与前面主体之间存在大间隔，检查是否为重新上市
    if qty_by_month:
        tail_months   = sorted_months[tail_start:]
        body_months   = sorted_months[:tail_start]
        tail_avg  = sum(qty_by_month.get(m, 0) for m in tail_months)  / len(tail_months)
        body_avg  = sum(qty_by_month.get(m, 0) for m in body_months)  / len(body_months)
        if body_avg > 0 and tail_avg >= body_avg * relaunch_ratio:
            # 尾部销量达到主体均值的一定比例，视为重新上市
            return sorted_months[-1]

    # 尾部连续块销量不足，视为孤立尾部，递归处理剩余部分
    return _effective_last_month(
        sorted_months[:tail_start],
        gap_threshold=gap_threshold,
        qty_by_month=qty_by_month,
        relaunch_ratio=relaunch_ratio,
    )


def _current_month() -> str:
    """返回 CST 当前月份，格式 'YYYY-MM'"""
    now = datetime.now(_CST)
    return f'{now.year}-{now.month:02d}'


# ── 核心函数 ──────────────────────────────────────────────────────────────────

def update_lifecycle(progress_cb=None) -> dict:
    """
    批量更新所有 status='recorded' 成品的上市/退市日期。
    按 model_id 分组处理，每个型号提交一次事务。
    返回 { 'updated': N, 'total_models': M }
    """
    # ── Step 1: 获取所有售后操作人 ─────────────────────────────────────────
    aftersale_rows = db.session.query(ShippingOperatorType.operator).filter_by(type='aftersale').all()
    aftersale_set = {row[0] for row in aftersale_rows}

    # ── Step 2: 一次查询取得每个型号的月度数量 ─────────────────────────────
    # 首尾月份和月份集合均可从这份结果推导，避免对 66 万行派生表重复 JOIN/聚合。
    qty_query = (
        db.session.query(
            ProductFinished.model_id,
            func.date_format(ShippingOrderFinished.shipped_date, '%Y-%m').label('month'),
            func.sum(ShippingOrderFinished.quantity).label('total_qty'),
        )
        .join(ShippingOrderFinished,
              ShippingOrderFinished.finished_code == ProductFinished.code)
        .with_hint(
            ShippingOrderFinished,
            'USE INDEX (ix_sof_finished_code_date)',
            dialect_name='mysql',
        )
        .filter(
            ProductFinished.status == 'recorded',
            ProductFinished.model_id.isnot(None),
            ShippingOrderFinished.shipped_date.isnot(None),
        )
    )
    if aftersale_set:
        qty_query = qty_query.filter(
            ShippingOrderFinished.operator.notin_(aftersale_set)
        )
    qty_query = qty_query.group_by(ProductFinished.model_id,
                                   func.date_format(ShippingOrderFinished.shipped_date, '%Y-%m'))

    shipping_by_model: dict[int, tuple[str, str]] = {}
    months_by_model: dict[int, list[str]] = {}
    qty_by_model: dict[int, dict[str, float]] = {}
    for row in qty_query.all():
        qty_by_model.setdefault(row.model_id, {})[row.month] = float(row.total_qty or 0)
    for model_id, qty_by_month in qty_by_model.items():
        months = sorted(qty_by_month)
        months_by_model[model_id] = months
        shipping_by_model[model_id] = (months[0], months[-1])

    # ── Step 3: 一次性加载所有需要处理的成品，按 model_id 分组（避免 N+1）──
    all_finished = (
        db.session.query(ProductFinished)
        .filter(ProductFinished.status == 'recorded', ProductFinished.model_id.isnot(None))
        .all()
    )
    finished_by_model: dict[int, list] = {}
    for pf in all_finished:
        finished_by_model.setdefault(pf.model_id, []).append(pf)
    all_model_ids = list(finished_by_model.keys())
    total_models = len(all_model_ids)

    # ── Step 4: 计算当前月份及阈值 ────────────────────────────────────────
    current_month = _current_month()
    threshold_month = _subtract_months(current_month, 2)  # 当前月 - 2 个月

    updated_count = 0

    # ── Step 5: 按型号逐一处理 ────────────────────────────────────────────
    for idx, model_id in enumerate(all_model_ids):
        if progress_cb and (
            idx == 0 or idx + 1 == total_models or (idx + 1) % 10 == 0
        ):
            progress_cb('processing', current=idx + 1, total=total_models)

        finished_list = finished_by_model.get(model_id, [])
        if not finished_list:
            continue

        shipping_data = shipping_by_model.get(model_id)

        for pf in finished_list:
            # 纯外贸产品不参与生命周期推算，清空日期后跳过
            if pf.market == 'foreign':
                if pf.listed_yymm or pf.delisted_yymm:
                    pf.listed_yymm   = None
                    pf.delisted_yymm = None
                    pf.updated_at    = _now_cst()
                    updated_count   += 1
                continue

            updates = {}

            if shipping_data is None:
                # 若产品近6个月内有手动设定的上市日期，说明可能是新品尚无数据，跳过
                if pf.listed_yymm and pf.listed_yymm >= _subtract_months(current_month, 6):
                    continue
                # 规则：无发货数据（旧型号兜底）→ 上市 2020-01，退市 2023-12
                # 注：这批产品发货记录缺失，以固定兜底值填充，不做动态推算
                updates['listed_yymm']   = '2020-01'
                updates['delisted_yymm'] = '2023-12'
            else:
                first_month, last_month = shipping_data

                # 上市日期规则：
                # - first_month == '2024-01' 且上市日期为空 → 2023-12（数据起点月特殊处理）
                # - first_month > '2024-01' → 上市日期 = first_month 的前一个月
                # - first_month < '2024-01'（2024年前已有发货的老产品）→ 不自动推算，
                #   保留手动设置值；若未手动设置则维持 null（数据不完整，无法可靠推断）
                if first_month == '2024-01' and not pf.listed_yymm:
                    updates['listed_yymm'] = '2023-12'
                elif first_month > '2024-01':
                    updates['listed_yymm'] = _prev_month(first_month)

                # 退市日期：用「有效末尾月」过滤孤立尾部发货
                sorted_months = months_by_model.get(model_id, [])
                effective_last = (
                    _effective_last_month(
                        sorted_months,
                        qty_by_month=qty_by_model.get(model_id),
                    )
                    if sorted_months else last_month
                )

                # 仅在值发生变化时才写入，避免无意义的 UPDATE
                new_delisted = _next_month(effective_last) if effective_last < threshold_month else None
                if new_delisted != pf.delisted_yymm:
                    updates['delisted_yymm'] = new_delisted

            # 仅在有字段变更时才写入，避免刷新 updated_at
            changed_updates = {k: v for k, v in updates.items() if getattr(pf, k) != v}
            if changed_updates:
                for k, v in changed_updates.items():
                    setattr(pf, k, v)
                pf.updated_at = _now_cst()
                updated_count += 1

    # 型号元数据规模远小于订单明细，一次提交保证失败时不留下半更新状态。
    db.session.commit()

    return {'updated': updated_count, 'total_models': total_models}
