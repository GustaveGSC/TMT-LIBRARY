"""
建表脚本：创建变更提醒表（ecr_reminder）。
在 backend/ 目录下执行：python create_ecr_reminders.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from database.base import db
from database.models.rd import EcrReminder

app = create_app()

with app.app_context():
    EcrReminder.__table__.create(bind=db.engine, checkfirst=True)
    print("建表完成：ecr_reminder")
