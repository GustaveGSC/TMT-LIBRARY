from database.base import db
from utils import now_cst


class CostSnapshot(db.Model):
    """BOM 成本快照：每次导入一个 Excel = 一条记录"""
    __tablename__ = 'cost_snapshot'

    id            = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    order_no      = db.Column(db.String(64),  nullable=True)                    # 订单号
    snapshot_date = db.Column(db.Date,        nullable=True)                    # 核算日期
    notes         = db.Column(db.Text,        nullable=True)                    # 备注
    created_by    = db.Column(db.String(64),  nullable=True)                    # 导入人
    created_at    = db.Column(db.DateTime,    nullable=False, default=now_cst)

    skus = db.relationship('CostSnapshotSku', backref='snapshot',
                           cascade='all, delete-orphan', lazy='select')

    def to_dict(self, include_skus=False):
        d = {
            'id':            self.id,
            'order_no':      self.order_no or '',
            'snapshot_date': self.snapshot_date.strftime('%Y-%m-%d') if self.snapshot_date else '',
            'notes':         self.notes or '',
            'created_by':    self.created_by or '',
            'created_at':    self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
            'sku_count':     len(self.skus) if self.skus is not None else 0,
        }
        if include_skus:
            d['skus'] = [s.to_dict() for s in self.skus]
        return d


class CostSnapshotSku(db.Model):
    """快照内的成品/产成品 SKU"""
    __tablename__ = 'cost_snapshot_sku'

    id                  = db.Column(db.Integer,      primary_key=True, autoincrement=True)
    snapshot_id         = db.Column(db.Integer,      db.ForeignKey('cost_snapshot.id', ondelete='CASCADE'), nullable=False, index=True)
    finished_code       = db.Column(db.String(64),   nullable=False)   # 成品品号（含版本，如 1201GDZM01-A）
    finished_name       = db.Column(db.String(128),  nullable=True)    # 成品品名
    finished_spec       = db.Column(db.String(256),  nullable=True)    # 成品规格
    product_finished_id = db.Column(db.Integer,      nullable=True)    # 关联产品库（可空）
    qty_in_order        = db.Column(db.Integer,      nullable=True)    # 订单数量
    total_cost          = db.Column(db.Numeric(12, 4), nullable=True)  # 单件总成本

    lines = db.relationship('CostBomLine', backref='sku',
                            cascade='all, delete-orphan', lazy='select')

    def to_dict(self):
        return {
            'id':                  self.id,
            'snapshot_id':         self.snapshot_id,
            'finished_code':       self.finished_code,
            'finished_name':       self.finished_name or '',
            'finished_spec':       self.finished_spec or '',
            'product_finished_id': self.product_finished_id,
            'qty_in_order':        self.qty_in_order,
            'total_cost':          float(self.total_cost) if self.total_cost is not None else None,
        }


class CostBomNode(db.Model):
    """BOM 节点主数据（物料/半成品/成品），跨快照共享，同一品号只存一条"""
    __tablename__ = 'cost_bom_node'

    id               = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    code             = db.Column(db.String(64),  nullable=False, unique=True)   # 品号（去版本后缀，如 14WD11001）
    code_with_version = db.Column(db.String(64), nullable=True)                 # 含版本完整品号（如 14WD11001-A01）
    std_code         = db.Column(db.String(64),  nullable=True)                 # 标准号
    name             = db.Column(db.String(128), nullable=True)                 # 品名
    spec             = db.Column(db.String(512), nullable=True)                 # 规格
    category         = db.Column(db.String(256), nullable=True)                 # 品名分类
    # material / semi / finished
    node_type        = db.Column(db.Enum('material', 'semi', 'finished'), nullable=False, default='material')
    is_purchased_semi = db.Column(db.Boolean,    nullable=False, default=False)  # 外购半成品（整体采购，下级无需计价）
    purchase_type    = db.Column(db.String(32),  nullable=True)                  # 采购件/自制件/3D打印
    # sheet_metal / wood / other
    material_type    = db.Column(db.Enum('sheet_metal', 'wood', 'other'), nullable=True)
    weight_kg        = db.Column(db.Numeric(10, 4), nullable=True)  # 重量(kg)，钣金估价用
    area_m2          = db.Column(db.Numeric(10, 4), nullable=True)  # 面积(m²)，木器估价用
    notes            = db.Column(db.Text,        nullable=True)
    created_at       = db.Column(db.DateTime,    nullable=False, default=now_cst)
    updated_at       = db.Column(db.DateTime,    nullable=False, default=now_cst, onupdate=now_cst)

    suppliers = db.relationship('CostMaterialSupplier', backref='node',
                                cascade='all, delete-orphan', lazy='select')
    prices    = db.relationship('CostMaterialPrice', backref='node',
                                cascade='all, delete-orphan', lazy='select')

    def to_dict(self, include_suppliers=False, latest_price=None):
        d = {
            'id':                self.id,
            'code':              self.code,
            'code_with_version': self.code_with_version or '',
            'std_code':          self.std_code or '',
            'name':              self.name or '',
            'spec':              self.spec or '',
            'category':          self.category or '',
            'node_type':         self.node_type,
            'is_purchased_semi': self.is_purchased_semi,
            'purchase_type':     self.purchase_type or '',
            'material_type':     self.material_type,
            'weight_kg':         float(self.weight_kg) if self.weight_kg is not None else None,
            'area_m2':           float(self.area_m2) if self.area_m2 is not None else None,
            'notes':             self.notes or '',
            'updated_at':        self.updated_at.strftime('%Y-%m-%d %H:%M') if self.updated_at else '',
        }
        if latest_price is not None:
            d['latest_price'] = latest_price
        if include_suppliers:
            d['suppliers'] = [s.to_dict() for s in self.suppliers]
        return d


class CostBomLine(db.Model):
    """BOM 明细行：属于某快照某 SKU 的一条父-子关系"""
    __tablename__ = 'cost_bom_line'

    id             = db.Column(db.Integer,       primary_key=True, autoincrement=True)
    sku_id         = db.Column(db.Integer,       db.ForeignKey('cost_snapshot_sku.id', ondelete='CASCADE'), nullable=False, index=True)
    parent_node_id = db.Column(db.Integer,       db.ForeignKey('cost_bom_node.id'), nullable=False, index=True)
    child_node_id  = db.Column(db.Integer,       db.ForeignKey('cost_bom_node.id'), nullable=False, index=True)
    seq            = db.Column(db.Integer,       nullable=True)
    quantity       = db.Column(db.Numeric(12, 4), nullable=True)
    unit_price     = db.Column(db.Numeric(12, 4), nullable=True)
    total_price    = db.Column(db.Numeric(12, 4), nullable=True)

    parent_node = db.relationship('CostBomNode', foreign_keys=[parent_node_id], lazy='joined')
    child_node  = db.relationship('CostBomNode', foreign_keys=[child_node_id],  lazy='joined')

    def to_dict(self):
        return {
            'id':             self.id,
            'sku_id':         self.sku_id,
            'parent_node_id': self.parent_node_id,
            'child_node_id':  self.child_node_id,
            'seq':            self.seq,
            'quantity':       float(self.quantity)   if self.quantity   is not None else None,
            'unit_price':     float(self.unit_price) if self.unit_price is not None else None,
            'total_price':    float(self.total_price) if self.total_price is not None else None,
            'parent_code':    self.parent_node.code if self.parent_node else '',
            'parent_name':    self.parent_node.name if self.parent_node else '',
            'child_code':              self.child_node.code              if self.child_node else '',
            'child_code_with_version': self.child_node.code_with_version if self.child_node else '',
            'child_name':              self.child_node.name              if self.child_node else '',
            'child_node_type': self.child_node.node_type if self.child_node else '',
            'child_is_purchased_semi': self.child_node.is_purchased_semi if self.child_node else False,
            'child_purchase_type': self.child_node.purchase_type if self.child_node else '',
        }


class CostMaterialSupplier(db.Model):
    """物料供应商报价（手动维护，独立于快照）"""
    __tablename__ = 'cost_material_supplier'

    id            = db.Column(db.Integer,      primary_key=True, autoincrement=True)
    node_id       = db.Column(db.Integer,      db.ForeignKey('cost_bom_node.id', ondelete='CASCADE'), nullable=False, index=True)
    supplier_name = db.Column(db.String(64),   nullable=False)
    unit_price    = db.Column(db.Numeric(12, 4), nullable=False)
    price_date    = db.Column(db.Date,         nullable=True)
    is_preferred  = db.Column(db.Boolean,      nullable=False, default=False)
    notes         = db.Column(db.Text,         nullable=True)
    created_by    = db.Column(db.String(64),   nullable=True)
    created_at    = db.Column(db.DateTime,     nullable=False, default=now_cst)

    def to_dict(self):
        return {
            'id':            self.id,
            'node_id':       self.node_id,
            'supplier_name': self.supplier_name,
            'unit_price':    float(self.unit_price) if self.unit_price is not None else None,
            'price_date':    self.price_date.strftime('%Y-%m-%d') if self.price_date else '',
            'is_preferred':  self.is_preferred,
            'notes':         self.notes or '',
            'created_by':    self.created_by or '',
            'created_at':    self.created_at.strftime('%Y-%m-%d') if self.created_at else '',
        }


class CostMaterialPrice(db.Model):
    """物料价格历史（BOM导入自动写入 + 手动添加）"""
    __tablename__ = 'cost_material_price'

    id            = db.Column(db.Integer,        primary_key=True, autoincrement=True)
    node_id       = db.Column(db.Integer,        db.ForeignKey('cost_bom_node.id', ondelete='CASCADE'), nullable=False, index=True)
    unit_price    = db.Column(db.Numeric(12, 4), nullable=False)
    price_date    = db.Column(db.Date,           nullable=True)
    supplier_name = db.Column(db.String(64),     nullable=True)             # 手动填写时可补充
    source        = db.Column(db.Enum('bom_import', 'manual'), nullable=False, default='manual')
    snapshot_id   = db.Column(db.Integer,        db.ForeignKey('cost_snapshot.id', ondelete='SET NULL'), nullable=True)
    notes         = db.Column(db.Text,           nullable=True)
    created_by    = db.Column(db.String(64),     nullable=True)
    created_at    = db.Column(db.DateTime,       nullable=False, default=now_cst)

    def to_dict(self):
        return {
            'id':            self.id,
            'node_id':       self.node_id,
            'unit_price':    float(self.unit_price) if self.unit_price is not None else None,
            'price_date':    self.price_date.strftime('%Y-%m-%d') if self.price_date else '',
            'supplier_name': self.supplier_name or '',
            'source':        self.source,
            'snapshot_id':   self.snapshot_id,
            'notes':         self.notes or '',
            'created_by':    self.created_by or '',
            'created_at':    self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
        }


class CostMaterialRule(db.Model):
    """材料单位成本估算规则（钣金按重量/木器按面积）"""
    __tablename__ = 'cost_material_rule'

    id              = db.Column(db.Integer,      primary_key=True, autoincrement=True)
    material_type   = db.Column(db.Enum('sheet_metal', 'wood'), nullable=False)
    rule_name       = db.Column(db.String(64),   nullable=False)   # 如 "1.0mm冷轧板"、"W501橡木"
    unit            = db.Column(db.String(16),   nullable=False)   # "kg" 或 "m²"
    price_per_unit  = db.Column(db.Numeric(12, 4), nullable=False) # 元/单位
    effective_date  = db.Column(db.Date,         nullable=True)
    notes           = db.Column(db.Text,         nullable=True)
    created_at      = db.Column(db.DateTime,     nullable=False, default=now_cst)

    def to_dict(self):
        return {
            'id':             self.id,
            'material_type':  self.material_type,
            'rule_name':      self.rule_name,
            'unit':           self.unit,
            'price_per_unit': float(self.price_per_unit) if self.price_per_unit is not None else None,
            'effective_date': self.effective_date.strftime('%Y-%m-%d') if self.effective_date else '',
            'notes':          self.notes or '',
            'created_at':     self.created_at.strftime('%Y-%m-%d') if self.created_at else '',
        }
