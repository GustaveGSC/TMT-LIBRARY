from datetime import datetime, timezone, timedelta
from database.base import db
from database.models.product.finished import ProductFinished
from database.models.shipping import ShippingOrderFinished, ShippingOperatorType
from sqlalchemy import func, collate


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

    # ── Step 2: 单次聚合查询，按 model_id 取发货数据首尾月份 ───────────────
    agg_query = (
        db.session.query(
            ProductFinished.model_id,
            func.min(func.date_format(ShippingOrderFinished.shipped_date, '%Y-%m')).label('first_month'),
            func.max(func.date_format(ShippingOrderFinished.shipped_date, '%Y-%m')).label('last_month'),
        )
        .join(ShippingOrderFinished,
              collate(ShippingOrderFinished.finished_code, 'utf8mb4_unicode_ci') == ProductFinished.code)
        .filter(
            ProductFinished.status == 'recorded',
            ProductFinished.model_id.isnot(None),
            ShippingOrderFinished.shipped_date.isnot(None),
        )
    )
    # 仅当存在售后操作人时才加过滤，避免 NOT IN () 的边界问题
    if aftersale_set:
        agg_query = agg_query.filter(
            ShippingOrderFinished.operator.notin_(aftersale_set)
        )
    agg_query = agg_query.group_by(ProductFinished.model_id)

    shipping_by_model = {row.model_id: (row.first_month, row.last_month) for row in agg_query.all()}

    # ── Step 3: 获取所有需要处理的 model_id ───────────────────────────────
    model_id_rows = (
        db.session.query(ProductFinished.model_id)
        .filter(ProductFinished.status == 'recorded', ProductFinished.model_id.isnot(None))
        .distinct()
        .all()
    )
    all_model_ids = [row[0] for row in model_id_rows]
    total_models = len(all_model_ids)

    # ── Step 4: 计算当前月份及阈值 ────────────────────────────────────────
    current_month = _current_month()
    threshold_month = _subtract_months(current_month, 2)  # 当前月 - 2 个月

    updated_count = 0

    # ── Step 5: 按型号逐一处理 ────────────────────────────────────────────
    for idx, model_id in enumerate(all_model_ids):
        if progress_cb:
            progress_cb('processing', current=idx + 1, total=total_models)

        finished_list = (
            ProductFinished.query
            .filter_by(model_id=model_id, status='recorded')
            .all()
        )
        if not finished_list:
            continue

        shipping_data = shipping_by_model.get(model_id)

        for pf in finished_list:
            updates = {}

            if shipping_data is None:
                # 规则：无发货数据 → 上市 2020-01，退市 2023-12
                updates['listed_yymm']   = '2020-01'
                updates['delisted_yymm'] = '2023-12'
            else:
                first_month, last_month = shipping_data

                # 规则：first_month == '2024-01' 且上市日期为空 → 2023-12
                if first_month == '2024-01' and not pf.listed_yymm:
                    updates['listed_yymm'] = '2023-12'

                # 规则：first_month > '2024-01' → 上市日期 = first_month 的前一个月
                if first_month > '2024-01':
                    updates['listed_yymm'] = _prev_month(first_month)

                # 规则：last_month < 当前月 - 2 → 退市日期 = last_month 的下一个月
                # 规则：last_month >= 当前月 - 2（近 2 月内有数据）→ 退市日期清空
                if last_month < threshold_month:
                    updates['delisted_yymm'] = _next_month(last_month)
                else:
                    updates['delisted_yymm'] = None

            if updates:
                for k, v in updates.items():
                    setattr(pf, k, v)
                pf.updated_at = _now_cst()
                updated_count += 1

        # 每个型号提交一次，避免单事务过大超时
        db.session.commit()

    return {'updated': updated_count, 'total_models': total_models}
