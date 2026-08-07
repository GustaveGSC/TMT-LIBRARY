"""售后物料组合；组合只引用 ERP 编码，不复制 ERP 物料主数据。"""

from sqlalchemy.dialects import mysql

from database.base import db
from utils import now_cst


def _erp_code_string():
    """MySQL JOIN 键显式对齐 import_product_raw.code 的历史排序规则。"""
    return db.String(255).with_variant(
        mysql.VARCHAR(255, collation='utf8mb4_0900_ai_ci'), 'mysql'
    )


class MaterialCombo(db.Model):
    """人工维护的售后备件组合，不与产品型号建立关系。"""

    __tablename__ = 'material_combo'
    __table_args__ = (
        db.UniqueConstraint('name', name='uq_material_combo_name'),
        db.Index('ix_material_combo_disabled', 'is_disabled'),
        db.Index('ix_material_combo_category', 'category'),
    )

    id          = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name        = db.Column(db.String(200), nullable=False)
    category    = db.Column(db.String(100), nullable=True)
    remark      = db.Column(db.Text, nullable=True)
    is_disabled = db.Column(db.Boolean, nullable=False, default=False)
    sort_order  = db.Column(db.Integer, nullable=False, default=0)
    created_by  = db.Column(db.String(100), nullable=True)
    created_at  = db.Column(db.DateTime, nullable=False, default=now_cst)
    updated_at  = db.Column(db.DateTime, nullable=False, default=now_cst, onupdate=now_cst)

    items = db.relationship(
        'MaterialComboItem', cascade='all, delete-orphan', passive_deletes=True,
        order_by='MaterialComboItem.sort_order, MaterialComboItem.id',
    )

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'category': self.category,
            'remark': self.remark, 'is_disabled': bool(self.is_disabled),
            'sort_order': self.sort_order, 'created_by': self.created_by,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
            if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S')
            if self.updated_at else None,
        }


class MaterialComboItem(db.Model):
    """组合明细；ERP 物料可能在重导后消失，因此 material_code 不设外键。"""

    __tablename__ = 'material_combo_item'
    __table_args__ = (
        db.UniqueConstraint(
            'combo_id', 'material_code', name='uq_material_combo_item_combo_code'
        ),
        db.Index('ix_material_combo_item_combo', 'combo_id'),
    )

    id            = db.Column(db.Integer, primary_key=True, autoincrement=True)
    combo_id      = db.Column(
        db.Integer, db.ForeignKey('material_combo.id', ondelete='CASCADE'), nullable=False,
    )
    material_code = db.Column(_erp_code_string(), nullable=False)
    quantity      = db.Column(db.Integer, nullable=False, default=1)
    sort_order    = db.Column(db.Integer, nullable=False, default=0)
    created_at    = db.Column(db.DateTime, nullable=False, default=now_cst)

    def to_dict(self):
        return {
            'id': self.id, 'material_code': self.material_code,
            'quantity': self.quantity, 'sort_order': self.sort_order,
        }
