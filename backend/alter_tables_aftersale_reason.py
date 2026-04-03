"""
数据库变更脚本：售后工单原因行扩展
  1. aftersale_case_reason 加 model_id（关联 product_model）
  2. aftersale_case_reason 加 shipping_material_alias（发货物料简称）
  3. aftersale_case_reason 加 aftersale_material_alias（售后物料简称）

在 backend/ 目录下执行：python alter_tables_aftersale_reason.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from database.base import db

app = create_app()

# 逐列检查是否已存在，不存在再 ADD COLUMN（兼容 MySQL < 8.0.3）
NEW_COLUMNS = [
    ("model_id",                 "INT NULL"),
    ("shipping_material_alias",  "VARCHAR(200) NULL"),
    ("aftersale_material_alias", "VARCHAR(200) NULL"),
]

with app.app_context():
    for col_name, col_def in NEW_COLUMNS:
        # 查 information_schema 判断列是否已存在
        check_sql = db.text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = 'aftersale_case_reason'
              AND COLUMN_NAME  = :col
        """)
        count = db.session.execute(check_sql, {'col': col_name}).scalar()
        if count:
            print(f'  [SKIP] 列 {col_name} 已存在，跳过。')
            continue
        alter_sql = db.text(
            f"ALTER TABLE aftersale_case_reason ADD COLUMN {col_name} {col_def}"
        )
        try:
            db.session.execute(alter_sql)
            db.session.commit()
            print(f'  [OK]   已添加列 {col_name} {col_def}')
        except Exception as e:
            db.session.rollback()
            print(f'  [WARN] {col_name}: {e}')
    print('迁移完成。')
