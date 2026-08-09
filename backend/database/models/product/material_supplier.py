"""物料成本域的供应商主数据。"""

from database.base import db
from utils import now_cst


class MaterialSupplier(db.Model):
    __tablename__ = 'material_supplier'
    __table_args__ = (db.UniqueConstraint('name', name='uq_material_supplier_name'),)

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(64), nullable=False)
    contact = db.Column(db.String(64), nullable=True)
    remark = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now_cst)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_cst, onupdate=now_cst)

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'contact': self.contact or '',
            'remark': self.remark or '', 'created_by': self.created_by or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else '',
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else '',
        }
