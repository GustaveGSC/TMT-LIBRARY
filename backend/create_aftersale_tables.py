"""
建表脚本：创建售后数据模块的 3 张新表。
在 backend/ 目录下执行：python create_aftersale_tables.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from database.base import db

# 确保模型已注册到 SQLAlchemy metadata
import database.models.aftersale  # noqa

app = create_app()

with app.app_context():
    db.create_all()
    print("建表完成。")
    print("新增表：aftersale_reason, aftersale_case, aftersale_case_reason")
