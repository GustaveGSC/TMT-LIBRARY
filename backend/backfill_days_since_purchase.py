"""
回填脚本：为已有的 aftersale_case 记录计算 days_since_purchase
  条件：shipped_date 和 purchase_date 均不为空，且 days_since_purchase 为 NULL

在 backend/ 目录下执行：python backfill_days_since_purchase.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from database.base import db
from database.models.aftersale import AftersaleCase

app = create_app()

with app.app_context():
    cases = (
        AftersaleCase.query
        .filter(AftersaleCase.shipped_date.isnot(None))
        .filter(AftersaleCase.purchase_date.isnot(None))
        .filter(AftersaleCase.days_since_purchase.is_(None))
        .all()
    )

    print(f'找到 {len(cases)} 条需要回填的记录')

    updated = 0
    skipped = 0
    for case in cases:
        days = (case.shipped_date - case.purchase_date).days
        if days < 0:
            # 购买日期晚于售后日期，数据异常，记录但仍写入（负数）
            print(f'  [WARN] {case.ecommerce_order_no}: days={days}（购买日期晚于售后日期）')
        case.days_since_purchase = days
        updated += 1

    if updated:
        db.session.commit()
        print(f'回填完成：更新 {updated} 条，跳过 {skipped} 条。')
    else:
        print('无需回填。')
