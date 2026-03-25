"""
一次性建表脚本：为 shipping 模块创建 4 张新表。
在 backend/ 目录下执行：python create_tables.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from database.base import db

# 确保 shipping 模型已被导入（注册到 SQLAlchemy metadata）
import database.models.shipping  # noqa

app = create_app()

with app.app_context():
    # 只创建不存在的表，不影响已有表
    db.create_all()
    print("建表完成。")
    print("新增表：shipping_batch, shipping_record, shipping_operator_type, shipping_order_finished")
