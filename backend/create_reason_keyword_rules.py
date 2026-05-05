"""
建表脚本：创建售后原因关键词词典表（停用词 + 短词保留）并写入默认规则。
在 backend/ 目录下执行：python create_reason_keyword_rules.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from database.base import db
from database.models.aftersale import (
    AftersaleReasonStopword,
    AftersaleReasonShortKeepTerm,
)

DEFAULT_STOPWORDS = [
    '客户', '买家', '卖家', '商家', '售后', '问题', '原因', '情况',
    '要求', '申请', '处理', '反馈', '联系', '沟通',
    '补偿', '赔偿', '退款', '退货', '换货', '更换', '补发',
    '一个', '这个', '那个', '已经', '还是', '不是', '无法', '可以',
]
# ≤2 字默认视为泛词，此处为例外
DEFAULT_SHORT_KEEP_TERMS = ['椅套', '底座', '靠背', '拉链', '气杆']

app = create_app()

with app.app_context():
    AftersaleReasonStopword.__table__.create(bind=db.engine, checkfirst=True)
    AftersaleReasonShortKeepTerm.__table__.create(bind=db.engine, checkfirst=True)
    print("建表完成：aftersale_reason_stopword / short_keep_term")

    if AftersaleReasonStopword.query.count() == 0:
        for i, term in enumerate(DEFAULT_STOPWORDS):
            db.session.add(AftersaleReasonStopword(term=term, sort_order=i))
    if AftersaleReasonShortKeepTerm.query.count() == 0:
        for i, term in enumerate(DEFAULT_SHORT_KEEP_TERMS):
            db.session.add(AftersaleReasonShortKeepTerm(term=term, sort_order=i))

    db.session.commit()
    print("默认词典写入完成（若表原本为空）")
