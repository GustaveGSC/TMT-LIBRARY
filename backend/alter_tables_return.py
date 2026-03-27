"""
数据库变更脚本：为 shipping_record 添加 record_type 列，并扩展 UNIQUE 约束。
在 backend/ 目录下执行：python alter_tables_return.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from database.base import db

app = create_app()

SQL = """
ALTER TABLE shipping_record
  ADD COLUMN record_type ENUM('shipping', 'return') NOT NULL DEFAULT 'shipping',
  DROP INDEX uq_shipping_order_line,
  ADD UNIQUE KEY uq_shipping_order_line
    (ecommerce_order_no, line_no, product_code, record_type);
"""

with app.app_context():
    db.session.execute(db.text(SQL))
    db.session.commit()
    print("迁移完成：shipping_record 已添加 record_type 列，UNIQUE 约束已更新。")