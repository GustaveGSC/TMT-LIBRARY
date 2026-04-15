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


class AftersaleKeywordCandidate(db.Model):
    """关键词候选池：记录 n-gram 在各原因下的出现次数，达到阈值后晋升到原因 keywords"""
    __tablename__ = 'aftersale_keyword_candidate'

    id        = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    reason_id = db.Column(db.Integer,     db.ForeignKey('aftersale_reason.id',
                                           ondelete='CASCADE'), nullable=False, index=True)
    keyword   = db.Column(db.String(20),  nullable=False)
    count     = db.Column(db.Integer,     nullable=False, default=1)

    __table_args__ = (
        db.UniqueConstraint('reason_id', 'keyword', name='uq_keyword_candidate'),
    )


class AftersaleShippingAlias(db.Model):
    """发货物料简称库：规范名称 + 物料名称关键词列表（用于自动匹配）"""
    __tablename__ = 'aftersale_shipping_alias'

    id         = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    name       = db.Column(db.String(200), nullable=False, unique=True)
    keywords   = db.Column(db.JSON,        nullable=True)   # 物料名称关键词列表
    sort_order = db.Column(db.Integer,     nullable=False, default=0)
    created_at = db.Column(db.DateTime,    nullable=False, default=now_cst)

    def to_dict(self):
        return {
            'id':        self.id,
            'name':      self.name,
            'keywords':  self.keywords or [],
            'sort_order': self.sort_order,
        }


class AftersaleShippingIgnoreTerm(db.Model):
    """发货物料匹配过滤词：物料名称包含这些词时跳过简称匹配"""
    __tablename__ = 'aftersale_shipping_ignore_term'

    id         = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    term       = db.Column(db.String(100), nullable=False, unique=True)
    created_at = db.Column(db.DateTime,    nullable=False, default=now_cst)

    def to_dict(self):
        return {'id': self.id, 'term': self.term}


class AftersaleReasonStopword(db.Model):
    """售后原因词典：停用词（用于关键词学习/匹配降噪）"""
    __tablename__ = 'aftersale_reason_stopword'

    id         = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    term       = db.Column(db.String(100), nullable=False, unique=True)
    enabled    = db.Column(db.Boolean,     nullable=False, default=True)
    sort_order = db.Column(db.Integer,     nullable=False, default=0)
    created_at = db.Column(db.DateTime,    nullable=False, default=now_cst)

    def to_dict(self):
        return {
            'id': self.id,
            'term': self.term,
            'enabled': bool(self.enabled),
            'sort_order': self.sort_order,
        }


class AftersaleReasonFaultTerm(db.Model):
    """售后原因词典：故障核心词（命中后提升原因区分度）"""
    __tablename__ = 'aftersale_reason_fault_term'

    id         = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    term       = db.Column(db.String(100), nullable=False, unique=True)
    enabled    = db.Column(db.Boolean,     nullable=False, default=True)
    sort_order = db.Column(db.Integer,     nullable=False, default=0)
    created_at = db.Column(db.DateTime,    nullable=False, default=now_cst)

    def to_dict(self):
        return {
            'id': self.id,
            'term': self.term,
            'enabled': bool(self.enabled),
            'sort_order': self.sort_order,
        }


class AftersaleReasonComponentTerm(db.Model):
    """售后原因词典：部件词（与核心词组合提升召回）"""
    __tablename__ = 'aftersale_reason_component_term'

    id         = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    term       = db.Column(db.String(100), nullable=False, unique=True)
    enabled    = db.Column(db.Boolean,     nullable=False, default=True)
    sort_order = db.Column(db.Integer,     nullable=False, default=0)
    created_at = db.Column(db.DateTime,    nullable=False, default=now_cst)

    def to_dict(self):
        return {
            'id': self.id,
            'term': self.term,
            'enabled': bool(self.enabled),
            'sort_order': self.sort_order,
        }


class AftersaleReasonShortKeepTerm(db.Model):
    """售后原因词典：短词保留（≤2 字时默认视为泛词，在此表中的词除外）"""
    __tablename__ = 'aftersale_reason_short_keep_term'

    id         = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    term       = db.Column(db.String(100), nullable=False, unique=True)
    enabled    = db.Column(db.Boolean,     nullable=False, default=True)
    sort_order = db.Column(db.Integer,     nullable=False, default=0)
    created_at = db.Column(db.DateTime,    nullable=False, default=now_cst)

    def to_dict(self):
        return {
            'id': self.id,
            'term': self.term,
            'enabled': bool(self.enabled),
            'sort_order': self.sort_order,
        }


class AftersaleReasonSynonymRule(db.Model):
    """售后原因词典：同义词归一规则（pattern -> replacement）"""
    __tablename__ = 'aftersale_reason_synonym_rule'

    id          = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    pattern     = db.Column(db.String(200), nullable=False, unique=True)
    replacement = db.Column(db.String(100), nullable=False)
    is_regex    = db.Column(db.Boolean,     nullable=False, default=True)
    enabled     = db.Column(db.Boolean,     nullable=False, default=True)
    sort_order  = db.Column(db.Integer,     nullable=False, default=0)
    created_at  = db.Column(db.DateTime,    nullable=False, default=now_cst)

    def to_dict(self):
        return {
            'id': self.id,
            'pattern': self.pattern,
            'replacement': self.replacement,
            'is_regex': bool(self.is_regex),
            'enabled': bool(self.enabled),
            'sort_order': self.sort_order,
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

    shipped_date          = db.Column(db.Date,    nullable=True)
    operator           = db.Column(db.String(100), nullable=True)
    channel_name       = db.Column(db.String(200), nullable=True)
    province           = db.Column(db.String(50),  nullable=True)
    city               = db.Column(db.String(100), nullable=True)
    district           = db.Column(db.String(100), nullable=True)
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
            'city':               self.city,
            'district':           self.district,
            'status':              self.status,


            'processed_at':        self.processed_at.strftime('%Y-%m-%d %H:%M:%S') if self.processed_at else None,
            'created_at':          self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }
        if include_reasons:
            d['reasons'] = [r.to_dict() for r in self.case_reasons]
        return d


class AftersaleReasonAliasAffinity(db.Model):
    """原因-发货简称亲和度：记录已确认工单中 reason_id + shipping_alias_id 的共现次数，
    用于在候选简称基础分相同时做二次排序。"""
    __tablename__ = 'aftersale_reason_alias_affinity'

    id                = db.Column(db.Integer, primary_key=True, autoincrement=True)
    reason_id         = db.Column(db.Integer, db.ForeignKey('aftersale_reason.id',
                                  ondelete='CASCADE'), nullable=False, index=True)
    shipping_alias_id = db.Column(db.Integer, db.ForeignKey('aftersale_shipping_alias.id',
                                  ondelete='CASCADE'), nullable=False, index=True)
    count             = db.Column(db.Integer, nullable=False, default=1)
    updated_at        = db.Column(db.DateTime, nullable=False, default=now_cst, onupdate=now_cst)

    __table_args__ = (
        db.UniqueConstraint('reason_id', 'shipping_alias_id', name='uq_reason_alias_affinity'),
    )

    def to_dict(self):
        return {
            'reason_id':         self.reason_id,
            'shipping_alias_id': self.shipping_alias_id,
            'count':             self.count,
        }


class AftersaleCaseReason(db.Model):
    """工单-原因关联，一个工单可拆分为多条原因记录（每条对应一个型号+物料简称+原因）"""
    __tablename__ = 'aftersale_case_reason'

    id                       = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    case_id                  = db.Column(db.Integer,     db.ForeignKey('aftersale_case.id', ondelete='CASCADE'), nullable=False)
    reason_id                = db.Column(db.Integer,     db.ForeignKey('aftersale_reason.id'), nullable=True)
    reason_category_id       = db.Column(db.Integer,     db.ForeignKey('aftersale_reason_category.id', ondelete='SET NULL'), nullable=True)  # reason_id 为空时的一级分类
    # 售后内容扩展字段（v2）
    model_id          = db.Column(db.Integer, db.ForeignKey('product_model.id',           ondelete='SET NULL'), nullable=True)
    shipping_alias_id = db.Column(db.Integer, db.ForeignKey('aftersale_shipping_alias.id', ondelete='SET NULL'), nullable=True)

    purchase_date       = db.Column(db.Date,    nullable=True)   # 该条内容的购买日期（每条可不同）
    days_since_purchase = db.Column(db.Integer, nullable=True)   # 售后间隔天数 = shipped_date - purchase_date
    created_at        = db.Column(db.DateTime, nullable=False, default=now_cst)

    product_model    = db.relationship('ProductModel',          foreign_keys=[model_id],          lazy='select')
    shipping_alias   = db.relationship('AftersaleShippingAlias', foreign_keys=[shipping_alias_id], lazy='select')

    def to_dict(self):
        # 一级分类：优先从 reason_id 取，fallback 到 reason_category_id 直接关联
        cat_name = None
        if self.reason and self.reason.category_obj:
            cat_name = self.reason.category_obj.name
        elif self.reason_category_id:
            cat = AftersaleReasonCategory.query.get(self.reason_category_id)
            if cat:
                cat_name = cat.name
        return {
            'id':                  self.id,
            'case_id':             self.case_id,
            'reason_id':           self.reason_id,
            'reason_category_id':  self.reason_category_id,
            'reason_name':         self.reason.name if self.reason else None,
            'reason_category':     cat_name,
            'model_id':            self.model_id,
            'model_code':          self.product_model.model_code if self.product_model else None,
            'model_name':          self.product_model.name       if self.product_model else None,
            'shipping_alias_id':   self.shipping_alias_id,
            'shipping_alias_name': self.shipping_alias.name   if self.shipping_alias   else None,

            'purchase_date':         self.purchase_date.strftime('%Y-%m-%d') if self.purchase_date else None,
            'days_since_purchase':   self.days_since_purchase,
            'created_at':          self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


class AftersaleDictSuggestion(db.Model):
    """词典自动优化建议表（系统在工单确认时自动生成，由用户审核接受或拒绝）"""
    __tablename__ = 'aftersale_dict_suggestion'

    id         = db.Column(db.Integer,  primary_key=True, autoincrement=True)
    type       = db.Column(db.Enum('stopword', 'ignore_term', 'promoted_keyword',
                                   'synonym_candidate'),
                           nullable=False, index=True)
    value      = db.Column(db.String(100), nullable=False)
    reason     = db.Column(db.String(500))           # 机器生成的说明文字
    meta       = db.Column(db.JSON, nullable=True)   # 附加数据，synonym_candidate 存涉及的 reason_ids
    count      = db.Column(db.Integer, nullable=False, default=1)   # 触发次数
    status     = db.Column(db.Enum('pending', 'accepted', 'rejected'),
                           nullable=False, default='pending', index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now_cst)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_cst, onupdate=now_cst)

    __table_args__ = (
        db.UniqueConstraint('type', 'value', name='uq_dict_sug_type_value'),
    )

    def to_dict(self):
        return {
            'id':         self.id,
            'type':       self.type,
            'value':      self.value,
            'reason':     self.reason,
            'meta':       self.meta,
            'count':      self.count,
            'status':     self.status,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }
