from database.base import db
from utils import now_cst


class MaterialGate(db.Model):
    """按物料编码维护的研发门禁；同一编码只允许一条在架记录。"""
    __tablename__ = 'material_gate'

    id         = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    code       = db.Column(db.String(64),  nullable=False, index=True)
    name       = db.Column(db.String(200), nullable=False, server_default='')
    level      = db.Column(db.String(16),  nullable=False)  # warn / block
    reason     = db.Column(db.String(500), nullable=False)
    is_active  = db.Column(db.Boolean,     nullable=False, default=True)
    created_by = db.Column(db.String(64),  nullable=True)
    created_at = db.Column(db.DateTime,    nullable=False, default=now_cst)
    updated_at = db.Column(db.DateTime,    nullable=False, default=now_cst, onupdate=now_cst)

    def to_dict(self):
        return {
            'id':         self.id,
            'code':       self.code,
            'name':       self.name or '',
            'level':      self.level,
            'reason':     self.reason,
            'is_active':  self.is_active,
            'created_by': self.created_by or '',
            'created_at': self.created_at.strftime('%Y-%m-%d') if self.created_at else '',
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M') if self.updated_at else '',
        }


class EcrNote(db.Model):
    """用户在变更申请单页面记录的个人笔记（按用户名隔离）"""
    __tablename__ = 'ecr_note'

    id         = db.Column(db.Integer,      primary_key=True, autoincrement=True)
    username   = db.Column(db.String(64),   nullable=False, index=True)   # 所属用户
    content    = db.Column(db.Text,         nullable=False)                # 笔记内容
    created_at = db.Column(db.DateTime,     nullable=False, default=now_cst)

    def to_dict(self):
        return {
            'id':         self.id,
            'content':    self.content,
            'time':       self.created_at.strftime('%m-%d %H:%M') if self.created_at else '',
            'created_at': self.created_at.isoformat() if self.created_at else '',
        }
