"""
数据库变更脚本：为 shipping_order_finished 添加 city 和 district 列。
在 backend/ 目录下执行：python alter_tables_region.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from database.base import db

app = create_app()

SQL = """
ALTER TABLE shipping_order_finished
  ADD COLUMN city     VARCHAR(100) NULL AFTER province,
  ADD COLUMN district VARCHAR(100) NULL AFTER city;
"""

with app.app_context():
    db.session.execute(db.text(SQL))
    db.session.commit()
    print("迁移完成：shipping_order_finished 已添加 city 和 district 列。")
    print("请执行一次「刷新全局数据」以重新填充已有记录的城市/县区信息。")
