from datetime import datetime, timezone, timedelta
from database.base import db

CST = timezone(timedelta(hours=8))
def now_cst(): return datetime.now(CST).replace(tzinfo=None)


class AftersaleReasonCategory(db.Model):
    """售后原因一级分类（大方向）"""
    __tablename__ = 'aftersale_reason_category'

    id         = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    name       = db.Column(db.String(100), nullable=False, unique=True)
    sort_order = db.Column(db.Integer,     nullable=False, default=0)
    created_at = db.Column(db.DateTime,    nullable=False, default=now_cst)

    # 一级分类下的二级原因
    reasons = db.relationship('AftersaleReason', backref='category_obj', lazy=True)

    def to_dict(self):
        return {
            'id':         self.id,
            'name':       self.name,
            'sort_order': self.sort_order,
        }


class AftersaleReason(db.Model):
    """售后原因二级条目（具体原因），含关键词用于自动匹配"""
    __tablename__ = 'aftersale_reason'

    id          = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    name        = db.Column(db.String(100), nullable=False, unique=True)
    # 关联一级分类，nullable 允许暂未归类的原因
    category_id = db.Column(db.Integer,     db.ForeignKey('aftersale_reason_category.id',
                                             ondelete='SET NULL'), nullable=True)
    keywords    = db.Column(db.Text,        nullable=True)   # 逗号分隔关键词
    sort_order  = db.Column(db.Integer,     nullable=False, default=0)
    use_count   = db.Column(db.Integer,     nullable=False, default=0)  # 被引用次数
    created_at  = db.Column(db.DateTime,    nullable=False, default=now_cst)

    case_reasons = db.relationship('AftersaleCaseReason', backref='reason', lazy=True)

    def to_dict(self):
        return {
            'id':            self.id,
            'name':          self.name,
            'category_id':   self.category_id,
            'category_name': self.category_obj.name if self.category_obj else None,
            'keywords':      self.keywords or '',
            'sort_order':    self.sort_order,
            'use_count':     self.use_count,
            'created_at':    self.created_at.strftime('%Y-%m-%d') if self.created_at else None,
        }


class AftersaleProductAlias(db.Model):
    """物料组别简称：将一组产品代码映射为一个简称，用于售后处理中的简化展示"""
    __tablename__ = 'aftersale_product_alias'

    id            = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    alias         = db.Column(db.String(100), nullable=False, unique=True)
    # 该简称对应的产品代码列表，如 ["A001", "A002"]
    product_codes = db.Column(db.JSON,        nullable=False, default=list)
    sort_order    = db.Column(db.Integer,     nullable=False, default=0)
    created_at    = db.Column(db.DateTime,    nullable=False, default=now_cst)

    def to_dict(self):
        return {
            'id':            self.id,
            'alias':         self.alias,
            'product_codes': self.product_codes or [],
            'sort_order':    self.sort_order,
        }


class AftersaleCase(db.Model):
    """售后工单，每个电商订单号一条，聚合该订单所有物料"""
    __tablename__ = 'aftersale_case'
    __table_args__ = (
        db.Index('ix_aftersale_case_order_no',     'ecommerce_order_no'),
        db.Index('ix_aftersale_case_shipped_date', 'shipped_date'),
        db.Index('ix_aftersale_case_status',       'status'),
    )

    id                 = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    ecommerce_order_no = db.Column(db.String(100), nullable=False, unique=True)
    # 聚合该订单所有物料行：[{code, name, quantity}]
    products           = db.Column(db.JSON,        nullable=True)
    seller_remark      = db.Column(db.Text,        nullable=True)
    buyer_remark       = db.Column(db.Text,        nullable=True)
    # 售后产品分配：来自产品库的型号 [{model_id, model_code, model_name, series_name, category_name}]
    assigned_models    = db.Column(db.JSON,        nullable=True)
    # 发货物料分配：订单发货物料中涉及本次售后的条目（别名或品号字符串列表）
    shipping_materials = db.Column(db.JSON,        nullable=True)
    # 产生售后物料分配：本次售后需处理的物料 [{code, name, quantity}]
    aftersale_materials = db.Column(db.JSON,       nullable=True)
    shipped_date       = db.Column(db.Date,        nullable=True)
    operator           = db.Column(db.String(100), nullable=True)
    channel_name       = db.Column(db.String(200), nullable=True)
    province           = db.Column(db.String(50),  nullable=True)
    status             = db.Column(
                           db.Enum('pending', 'confirmed', 'ignored'),
                           nullable=False, default='pending'
                         )
    processed_at       = db.Column(db.DateTime,    nullable=True)
    created_at         = db.Column(db.DateTime,    nullable=False, default=now_cst)
    updated_at         = db.Column(db.DateTime,    nullable=False, default=now_cst, onupdate=now_cst)

    case_reasons = db.relationship('AftersaleCaseReason', backref='case',
                                   lazy=True, cascade='all, delete-orphan')

    def to_dict(self, include_reasons=False):
        d = {
            'id':                 self.id,
            'ecommerce_order_no': self.ecommerce_order_no,
            'products':           self.products or [],
            'seller_remark':      self.seller_remark,
            'buyer_remark':       self.buyer_remark,
            'shipped_date':       self.shipped_date.strftime('%Y-%m-%d') if self.shipped_date else None,
            'operator':           self.operator,
            'channel_name':       self.channel_name,
            'province':           self.province,
            'status':              self.status,
            'assigned_models':     self.assigned_models    or [],
            'shipping_materials':  self.shipping_materials  or [],
            'aftersale_materials': self.aftersale_materials or [],
            'processed_at':        self.processed_at.strftime('%Y-%m-%d %H:%M:%S') if self.processed_at else None,
            'created_at':          self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }
        if include_reasons:
            d['reasons'] = [r.to_dict() for r in self.case_reasons]
        return d


class AftersaleCaseReason(db.Model):
    """工单-原因关联，一个工单可拆分为多条原因记录"""
    __tablename__ = 'aftersale_case_reason'

    id                = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    case_id           = db.Column(db.Integer,     db.ForeignKey('aftersale_case.id', ondelete='CASCADE'), nullable=False)
    reason_id         = db.Column(db.Integer,     db.ForeignKey('aftersale_reason.id'), nullable=True)
    custom_reason     = db.Column(db.String(200), nullable=True)   # reason_id 为空时使用
    # 本原因涉及的产品 codes 子集（来自 aftersale_case.products）
    involved_products = db.Column(db.JSON,        nullable=True)
    notes             = db.Column(db.Text,        nullable=True)
    created_at        = db.Column(db.DateTime,    nullable=False, default=now_cst)

    def to_dict(self):
        cat_name = None
        if self.reason and self.reason.category_obj:
            cat_name = self.reason.category_obj.name
        return {
            'id':                self.id,
            'case_id':           self.case_id,
            'reason_id':         self.reason_id,
            'reason_name':       self.reason.name if self.reason else None,
            'reason_category':   cat_name,
            'custom_reason':     self.custom_reason,
            'involved_products': self.involved_products or [],
            'notes':             self.notes,
            'created_at':        self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }
