"""
数据库变更脚本：售后工单表扩展 v3
  aftersale_case 加 days_since_purchase（售后间隔天数 = 售后日期 - 购买日期）

在 backend/ 目录下执行：python alter_tables_aftersale_case_v3.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from database.base import db

app = create_app()

NEW_COLUMNS = [
    ("aftersale_case", "days_since_purchase", "INT NULL"),
]

with app.app_context():
    for table, col_name, col_def in NEW_COLUMNS:
        check_sql = db.text("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = :tbl
              AND COLUMN_NAME  = :col
        """)
        count = db.session.execute(check_sql, {'tbl': table, 'col': col_name}).scalar()
        if count:
            print(f'  [SKIP] {table}.{col_name} 已存在，跳过。')
            continue
        alter_sql = db.text(
            f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"
        )
        try:
            db.session.execute(alter_sql)
            db.session.commit()
            print(f'  [OK]   {table}.{col_name} {col_def} 已添加')
        except Exception as e:
            db.session.rollback()
            print(f'  [WARN] {table}.{col_name}: {e}')
    print('迁移完成。')
