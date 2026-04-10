from datetime import datetime, timezone, timedelta
from database.base import db

CST = timezone(timedelta(hours=8))
def now_cst(): return datetime.now(CST).replace(tzinfo=None)

# 编码类型常量
TYPE_FINISHED  = 'finished'   # 成品
TYPE_PACKAGED  = 'packaged'   # 产成品
TYPE_SEMI      = 'semi'       # 半成品
TYPE_MATERIAL  = 'material'   # 物料

VALID_TYPES = {TYPE_FINISHED, TYPE_PACKAGED, TYPE_SEMI, TYPE_MATERIAL}

TYPE_LABELS = {
    TYPE_FINISHED: '成品',
    TYPE_PACKAGED: '产成品',
    TYPE_SEMI:     '半成品',
    TYPE_MATERIAL: '物料',
}


class ErpCodeRule(db.Model):
    __tablename__ = 'erp_code_rules'

    id          = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    prefix      = db.Column(db.String(64),  nullable=False)
    type        = db.Column(db.String(20),  nullable=False)
    description = db.Column(db.String(255), nullable=True)
    is_disabled = db.Column(db.Boolean,     nullable=False, default=False)
    created_at  = db.Column(db.DateTime,    nullable=False, default=now_cst)

    __table_args__ = (
        db.UniqueConstraint('prefix', 'type', name='uq_prefix_type'),
    )

    def to_dict(self) -> dict:
        return {
            'id':          self.id,
            'prefix':      self.prefix,
            'type':        self.type,
            'type_label':  TYPE_LABELS.get(self.type, self.type),
            'description': self.description,
            'is_disabled': bool(self.is_disabled),
            'created_at':  self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }