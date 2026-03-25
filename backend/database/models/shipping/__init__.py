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

    records = db.relationship('ShippingRecord', backref='batch', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id':          self.id,
            'type':        self.type,
            'filename':    self.filename,
            'row_count':   self.row_count,
            'imported_at': self.imported_at.strftime('%Y-%m-%d %H:%M:%S') if self.imported_at else None,
        }


class ShippingRecord(db.Model):
    """原始发货记录（发货+售后共用，按 operator 区分），单表存所有年份"""
    __tablename__ = 'shipping_record'
    __table_args__ = (
        db.UniqueConstraint('ecommerce_order_no', 'line_no', 'product_code', name='uq_shipping_order_line'),
        db.Index('ix_shipping_record_shipped_date', 'shipped_date'),
        db.Index('ix_shipping_record_operator',     'operator'),
        db.Index('ix_shipping_record_product_code', 'product_code'),
        db.Index('ix_shipping_record_province',     'province'),
    )

    id                 = db.Column(db.Integer,        primary_key=True, autoincrement=True)
    batch_id           = db.Column(db.Integer,        db.ForeignKey('shipping_batch.id'), nullable=False)
    ecommerce_order_no = db.Column(db.String(100),    nullable=True)   # 电商主订单号 [04]
    line_no            = db.Column(db.String(50),     nullable=True)   # 项次 [19]
    shipped_date       = db.Column(db.Date,           nullable=True)   # 单据日期 [05]
    channel_name       = db.Column(db.String(100),    nullable=True)   # 渠道名称 [07]
    channel_code       = db.Column(db.String(50),     nullable=True)   # 渠道商 [08]
    channel_org_name   = db.Column(db.String(255),    nullable=True)   # 渠道商名称 [09]
    operator           = db.Column(db.String(100),    nullable=True)   # 最近操作人 [18]
    product_code       = db.Column(db.String(100),    nullable=True)   # 商品型号（产成品编码）[21]
    product_name       = db.Column(db.String(255),    nullable=True)   # 商品名称 [22]
    spec               = db.Column(db.String(255),    nullable=True)   # 规格 [49]
    quantity           = db.Column(db.Numeric(12, 2), nullable=True)   # 数量 [26]
    country            = db.Column(db.String(50),     nullable=True)   # 国家 [33]
    province           = db.Column(db.String(50),     nullable=True)   # 省份 [34]
    city               = db.Column(db.String(50),     nullable=True)   # 市区 [35]
    district           = db.Column(db.String(50),     nullable=True)   # 县区 [36]
    street             = db.Column(db.String(100),    nullable=True)   # 街道 [37]
    address            = db.Column(db.Text,           nullable=True)   # 详细地址 [38]
    buyer_remark       = db.Column(db.Text,           nullable=True)   # 买家留言 [53]
    seller_remark      = db.Column(db.Text,           nullable=True)   # 商家备注 [55]


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
    """预计算成品组合结果，从 shipping_record 按订单匹配 product_finished_packaged 生成"""
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
    quantity           = db.Column(db.Numeric(12, 2), nullable=True)
    shipped_date       = db.Column(db.Date,           nullable=True)
    operator           = db.Column(db.String(100),    nullable=True)
    channel_name       = db.Column(db.String(100),    nullable=True)
    province           = db.Column(db.String(50),     nullable=True)
    is_stale           = db.Column(db.Boolean,        nullable=False, default=False)  # 产品库变更后标记
    resolved_at        = db.Column(db.DateTime,       nullable=True)

    def to_dict(self):
        return {
            'id':                 self.id,
            'ecommerce_order_no': self.ecommerce_order_no,
            'finished_code':      self.finished_code,
            'finished_name':      self.finished_name,
            'quantity':           float(self.quantity) if self.quantity is not None else None,
            'shipped_date':       self.shipped_date.strftime('%Y-%m-%d') if self.shipped_date else None,
            'operator':           self.operator,
            'channel_name':       self.channel_name,
            'province':           self.province,
            'is_stale':           self.is_stale,
        }