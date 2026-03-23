from datetime import datetime, timezone, timedelta
from database.base import db

CST = timezone(timedelta(hours=8))
def now_cst(): return datetime.now(CST).replace(tzinfo=None)


class ProductParamKey(db.Model):
    """参数键名，集中管理，按分组归类"""
    __tablename__ = 'product_param_key'

    id         = db.Column(db.Integer,    primary_key=True, autoincrement=True)
    name       = db.Column(db.String(64), nullable=False)
    group_name = db.Column(db.String(20), nullable=False)  # dimension|config|brand|other
    sort_order = db.Column(db.Integer,    nullable=False, default=0)
    created_at = db.Column(db.DateTime,   nullable=False, default=now_cst)

    # 关联的成品参数值
    params = db.relationship('ProductFinishedParam', backref='key', lazy='dynamic', cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('name', 'group_name', name='uq_param_key'),
    )

    def to_dict(self) -> dict:
        return {
            'id':         self.id,
            'name':       self.name,
            'group_name': self.group_name,
            'sort_order': self.sort_order,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


class ProductFinishedParam(db.Model):
    """成品的参数值，每行对应一个键名+值"""
    __tablename__ = 'product_finished_param'

    id          = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    finished_id = db.Column(db.Integer,     db.ForeignKey('product_finished.id', ondelete='CASCADE'), nullable=False)
    key_id      = db.Column(db.Integer,     db.ForeignKey('product_param_key.id', ondelete='CASCADE'), nullable=False)
    value       = db.Column(db.String(255), nullable=False, default='')
    sort_order  = db.Column(db.Integer,     nullable=False, default=0)
    created_at  = db.Column(db.DateTime,    nullable=False, default=now_cst)
    updated_at  = db.Column(db.DateTime,    nullable=False, default=now_cst, onupdate=now_cst)

    __table_args__ = (
        db.UniqueConstraint('finished_id', 'key_id', name='uq_finished_param'),
    )

    def to_dict(self) -> dict:
        return {
            'id':          self.id,
            'finished_id': self.finished_id,
            'key_id':      self.key_id,
            'key_name':    self.key.name       if self.key else None,
            'group_name':  self.key.group_name if self.key else None,
            'value':       self.value,
            'sort_order':  self.sort_order,
        }
