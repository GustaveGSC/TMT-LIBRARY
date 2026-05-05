from datetime import datetime, timezone, timedelta
from database.base import db

CST = timezone(timedelta(hours=8))
def now_cst(): return datetime.now(CST).replace(tzinfo=None)


class EcrReminder(db.Model):
    """变更提醒条目：持久化、支持下架（软删除），不允许硬删除"""
    __tablename__ = 'ecr_reminder'

    id         = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    content    = db.Column(db.String(500), nullable=False)          # 提醒内容
    notes      = db.Column(db.Text,        nullable=True)           # 备注说明
    is_active  = db.Column(db.Boolean,     nullable=False, default=True)  # False = 已下架
    created_by = db.Column(db.String(64),  nullable=True)           # 创建人用户名
    created_at = db.Column(db.DateTime,    nullable=False, default=now_cst)
    updated_at = db.Column(db.DateTime,    nullable=False, default=now_cst, onupdate=now_cst)

    def to_dict(self):
        return {
            'id':         self.id,
            'content':    self.content,
            'notes':      self.notes or '',
            'is_active':  self.is_active,
            'created_by': self.created_by or '',
            'created_at': self.created_at.strftime('%Y-%m-%d') if self.created_at else '',
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M') if self.updated_at else '',
        }
