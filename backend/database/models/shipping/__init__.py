from datetime import datetime, timezone, timedelta
from database.base import db

CST = timezone(timedelta(hours=8))
def now_cst(): return datetime.now(CST).replace(tzinfo=None)


class ShippingBatch(db.Model):
    """导入批次，记录每次文件导入的元信息"""
    __tablename__ = 'shipping_batch'

    id          = db.Column(db.Integer,                    primary_key=True, autoincrement=True)
    type        = db.Column(db.Enum('shipping', 'return'), nullable=False)
    filename    = db.Column(db.String(255),                nullable=False)
    row_count   = db.Column(db.Integer,                    nullable=False, default=0)
    imported_at = db.Column(db.DateTime,                   nullable=False)

    records        = db.relationship('ShippingRecord', backref='batch', lazy=True, cascade='all, delete-orphan')
    return_records = db.relationship('ReturnRecord',   backref='batch', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id':          self.id,
            'type':        self.type,
            'filename':    self.filename,
            'row_count':   self.row_count,
            'imported_at': self.imported_at.strftime('%Y-%m-%d %H:%M:%S') if self.imported_at else None,
        }


class ShippingRecord(db.Model):
    """原始发货记录，单表存所有年份"""
    __tablename__ = 'shipping_record'
    __table_args__ = (
        db.UniqueConstraint('ecommerce_order_no', 'line_no', 'product_code', 'record_type',
                            name='uq_shipping_order_line'),
        db.Index('ix_shipping_record_shipped_date', 'shipped_date'),
        db.Index('ix_shipping_record_operator',     'operator'),
        db.Index('ix_shipping_record_product_code', 'product_code'),
        db.Index('ix_shipping_record_province',     'province'),
    )

    id                 = db.Column(db.Integer,        primary_key=True, autoincrement=True)
    batch_id           = db.Column(db.Integer,        db.ForeignKey('shipping_batch.id'), nullable=False)
    record_type        = db.Column(db.Enum('shipping', 'return'), nullable=False, default='shipping')
    ecommerce_order_no = db.Column(db.String(100),    nullable=True)
    line_no            = db.Column(db.String(50),     nullable=True)
    shipped_date       = db.Column(db.Date,           nullable=True)
    channel_name       = db.Column(db.String(100),    nullable=True)
    channel_code       = db.Column(db.String(50),     nullable=True)
    channel_org_name   = db.Column(db.String(255),    nullable=True)
    operator           = db.Column(db.String(100),    nullable=True)
    product_code       = db.Column(db.String(100),    nullable=True)
    product_name       = db.Column(db.String(255),    nullable=True)
    spec               = db.Column(db.String(255),    nullable=True)
    quantity           = db.Column(db.Numeric(12, 2), nullable=True)
    country            = db.Column(db.String(50),     nullable=True)
    province           = db.Column(db.String(50),     nullable=True)
    city               = db.Column(db.String(50),     nullable=True)
    district           = db.Column(db.String(50),     nullable=True)
    street             = db.Column(db.String(100),    nullable=True)
    address            = db.Column(db.Text,           nullable=True)
    buyer_remark       = db.Column(db.Text,           nullable=True)
    seller_remark      = db.Column(db.Text,           nullable=True)


class ReturnRecord(db.Model):
    """销退清单原始记录，独立于 shipping_record 存储"""
    __tablename__ = 'return_record'
    __table_args__ = (
        db.UniqueConstraint('ecommerce_order_no', 'product_code', 'shipped_date',
                            name='uq_return_order_product_date'),
        db.Index('ix_return_record_order_no',     'ecommerce_order_no'),
        db.Index('ix_return_record_product_code', 'product_code'),
        db.Index('ix_return_record_shipped_date', 'shipped_date'),
    )

    id                 = db.Column(db.Integer,        primary_key=True, autoincrement=True)
    batch_id           = db.Column(db.Integer,        db.ForeignKey('shipping_batch.id'), nullable=False)
    ecommerce_order_no = db.Column(db.String(100),    nullable=True)   # 平台订单
    shipped_date       = db.Column(db.Date,           nullable=True)   # 交易日期
    product_code       = db.Column(db.String(100),    nullable=True)   # 品号
    quantity           = db.Column(db.Numeric(12, 2), nullable=True)   # 数量（负值）
    warehouse_name     = db.Column(db.String(100),    nullable=True)   # 仓库名称


class ReturnWarehouseFilter(db.Model):
    """销退仓库过滤配置：标记哪些仓库的销退记录需忽略"""
    __tablename__ = 'return_warehouse_filter'

    id             = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    warehouse_name = db.Column(db.String(100), nullable=False, unique=True)
    is_excluded    = db.Column(db.Boolean,     nullable=False, default=False)  # True=导入时忽略
    created_at     = db.Column(db.DateTime,    nullable=False, default=now_cst)

    def to_dict(self):
        return {
            'warehouse_name': self.warehouse_name,
            'is_excluded':    self.is_excluded,
        }


class ShippingOperatorType(db.Model):
    """操作人分类配置：mapping 操作人 → 发货/售后/未分类"""
    __tablename__ = 'shipping_operator_type'

    id         = db.Column(db.Integer,                                primary_key=True, autoincrement=True)
    operator   = db.Column(db.String(100),                            nullable=False, unique=True)
    type       = db.Column(db.Enum('shipping', 'aftersale', 'unknown'), nullable=False, default='unknown')
    created_at = db.Column(db.DateTime,                               nullable=False, default=now_cst)
    updated_at = db.Column(db.DateTime,                               nullable=False, default=now_cst, onupdate=now_cst)

    def to_dict(self):
        return {
            'id':       self.id,
            'operator': self.operator,
            'type':     self.type,
        }


class ShippingOrderFinished(db.Model):
    """预计算成品组合结果：含发货数量、销退数量、实际数量"""
    __tablename__ = 'shipping_order_finished'
    __table_args__ = (
        db.Index('ix_sof_order_no',     'ecommerce_order_no'),
        db.Index('ix_sof_shipped_date', 'shipped_date'),
        db.Index('ix_sof_operator',     'operator'),
        db.Index('ix_sof_province',     'province'),
    )

    id                 = db.Column(db.Integer,        primary_key=True, autoincrement=True)
    ecommerce_order_no = db.Column(db.String(100),    nullable=False)
    finished_code      = db.Column(db.String(100),    nullable=True)    # 匹配到的成品编码（NULL=未匹配）
    finished_name      = db.Column(db.String(255),    nullable=True)    # 冗余存储，避免查询时 JOIN
    quantity           = db.Column(db.Numeric(12, 2), nullable=True)    # 发货数量
    return_quantity    = db.Column(db.Numeric(12, 2), nullable=True, default=0)  # 销退数量
    actual_quantity    = db.Column(db.Numeric(12, 2), nullable=True)    # 实际数量 = 发货 - 销退
    shipped_date       = db.Column(db.Date,           nullable=True)
    operator           = db.Column(db.String(100),    nullable=True)
    channel_name       = db.Column(db.String(100),    nullable=True)
    channel_code       = db.Column(db.String(100),    nullable=True)
    channel_org_name   = db.Column(db.String(100),    nullable=True)
    province           = db.Column(db.String(50),     nullable=True)
    city               = db.Column(db.String(100),    nullable=True)
    district           = db.Column(db.String(100),    nullable=True)
    is_stale           = db.Column(db.Boolean,        nullable=False, default=False)
    resolved_at        = db.Column(db.DateTime,       nullable=True)

    def to_dict(self):
        def _f(v): return float(v) if v is not None else None
        return {
            'id':                 self.id,
            'ecommerce_order_no': self.ecommerce_order_no,
            'finished_code':      self.finished_code,
            'finished_name':      self.finished_name,
            'quantity':           _f(self.quantity),
            'return_quantity':    _f(self.return_quantity),
            'actual_quantity':    _f(self.actual_quantity),
            'shipped_date':       self.shipped_date.strftime('%Y-%m-%d') if self.shipped_date else None,
            'operator':           self.operator,
            'channel_name':       self.channel_name,
            'channel_code':       self.channel_code,
            'channel_org_name':   self.channel_org_name,
            'province':           self.province,
            'city':               self.city,
            'district':           self.district,
            'is_stale':           self.is_stale,
        }
