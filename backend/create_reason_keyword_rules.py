"""
建表脚本：创建售后原因关键词词典表（标准档）并写入默认规则。
在 backend/ 目录下执行：python create_reason_keyword_rules.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from database.base import db
from database.models.aftersale import (
    AftersaleReasonStopword,
    AftersaleReasonFaultTerm,
    AftersaleReasonComponentTerm,
    AftersaleReasonShortKeepTerm,
    AftersaleReasonSynonymRule,
)

DEFAULT_STOPWORDS = [
    '客户', '买家', '卖家', '商家', '售后', '问题', '原因', '情况',
    '要求', '申请', '处理', '反馈', '联系', '沟通',
    '补偿', '赔偿', '退款', '退货', '换货', '更换', '补发',
    '一个', '这个', '那个', '已经', '还是', '不是', '无法', '可以',
]
DEFAULT_FAULT_TERMS = ['开裂', '裂纹', '断裂', '漏油', '松动', '异响', '脱落', '变形', '损坏', '卡住']
DEFAULT_COMPONENT_TERMS = ['椅套', '靠背', '坐垫', '桌面板', '固定板', '后固定板', '拉链', '气弹簧', '气杆', '底座']
# ≤2 字默认视为泛词，此处为例外（原 _is_generic_keyword 硬编码白名单）
DEFAULT_SHORT_KEEP_TERMS = ['椅套', '底座', '靠背', '拉链', '气杆']
DEFAULT_SYNONYMS = [
    (r'裂开|裂了|裂纹', '开裂'),
    (r'坏了|损毁|损伤', '损坏'),
    (r'晃动|松了|松旷', '松动'),
    (r'咯吱|响声|异音', '异响'),
    (r'气杆|气压杆', '气弹簧'),
    (r'后固定桌面板|后固板', '后固定板'),
]

app = create_app()

with app.app_context():
    AftersaleReasonStopword.__table__.create(bind=db.engine, checkfirst=True)
    AftersaleReasonFaultTerm.__table__.create(bind=db.engine, checkfirst=True)
    AftersaleReasonComponentTerm.__table__.create(bind=db.engine, checkfirst=True)
    AftersaleReasonShortKeepTerm.__table__.create(bind=db.engine, checkfirst=True)
    AftersaleReasonSynonymRule.__table__.create(bind=db.engine, checkfirst=True)
    print("建表完成：aftersale_reason_* 词典表")

    if AftersaleReasonStopword.query.count() == 0:
        for i, term in enumerate(DEFAULT_STOPWORDS):
            db.session.add(AftersaleReasonStopword(term=term, sort_order=i))
    if AftersaleReasonFaultTerm.query.count() == 0:
        for i, term in enumerate(DEFAULT_FAULT_TERMS):
            db.session.add(AftersaleReasonFaultTerm(term=term, sort_order=i))
    if AftersaleReasonComponentTerm.query.count() == 0:
        for i, term in enumerate(DEFAULT_COMPONENT_TERMS):
            db.session.add(AftersaleReasonComponentTerm(term=term, sort_order=i))
    if AftersaleReasonShortKeepTerm.query.count() == 0:
        for i, term in enumerate(DEFAULT_SHORT_KEEP_TERMS):
            db.session.add(AftersaleReasonShortKeepTerm(term=term, sort_order=i))
    if AftersaleReasonSynonymRule.query.count() == 0:
        for i, (pattern, replacement) in enumerate(DEFAULT_SYNONYMS):
            db.session.add(AftersaleReasonSynonymRule(
                pattern=pattern,
                replacement=replacement,
                is_regex=True,
                sort_order=i,
            ))

    db.session.commit()
    print("默认词典写入完成（若表原本为空）")
