"""
建表并写入产品匹配留言词典（aftersale_product_remark_dict）种子数据。

运行方式（在项目根目录）：
    python backend/create_product_remark_dict.py

若表已存在则跳过建表；种子数据使用 INSERT IGNORE，可多次运行。
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from app import create_app
from database.base import db
from database.models.aftersale import AftersaleProductRemarkDict

SEED_DATA = [
    # ── 材质 ──────────────────────────────────────────────────────────────────
    ('material', '橡胶木',  None),
    ('material', '枫木纹',  None),
    ('material', '桦木',    None),
    ('material', '榉木',    None),
    ('material', '橡木',    None),
    ('material', '微麻白',  None),
    ('material', '水洗白',  None),

    # ── 颜色 ──────────────────────────────────────────────────────────────────
    ('color', '红色',  None),
    ('color', '蓝色',  None),
    ('color', '绿色',  None),
    ('color', '黄色',  None),
    ('color', '灰色',  None),
    ('color', '白色',  None),
    ('color', '本色',  None),
    ('color', '粉色',  None),

    # ── 驱动方式（匹配顺序：长词优先，脚本按 sort_order 排） ──────────────────
    ('drive_type', '智能手摇', None),
    ('drive_type', '电动',    None),
    ('drive_type', '手摇式',  None),
    ('drive_type', '手摇',    None),

    # ── 尺寸（value=买家留言中的数字，display=型号名中的米制表达） ─────────────
    ('size', '80',  '0.8米'),
    ('size', '90',  '0.9米'),
    ('size', '100', '1.0米'),
    ('size', '105', '1.05米'),
    ('size', '120', '1.2米'),
    ('size', '140', '1.4米'),
    ('size', '160', '1.6米'),
    ('size', '180', '1.8米'),
    ('size', '200', '2.0米'),
]


def main():
    app = create_app()
    with app.app_context():
        # 建表（若不存在）
        db.create_all()
        print('[create_product_remark_dict] 表检查完毕')

        inserted = 0
        for i, (type_, value, display) in enumerate(SEED_DATA):
            exists = AftersaleProductRemarkDict.query.filter_by(
                type=type_, value=value
            ).first()
            if exists:
                continue
            row = AftersaleProductRemarkDict(
                type=type_,
                value=value,
                display=display,
                enabled=True,
                sort_order=i,
            )
            db.session.add(row)
            inserted += 1

        db.session.commit()
        print(f'[create_product_remark_dict] 写入种子数据 {inserted} 条（已存在的跳过）')
        total = AftersaleProductRemarkDict.query.count()
        print(f'[create_product_remark_dict] 当前表中共 {total} 条记录')


if __name__ == '__main__':
    main()
