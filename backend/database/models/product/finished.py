from database.base import db
from utils import now_cst

# 标签分类
class ProductTagCategory(db.Model):
    __tablename__ = 'product_tag_category'

    id         = db.Column(db.Integer,    primary_key=True, autoincrement=True)
    name       = db.Column(db.String(32), nullable=False, unique=True)
    color      = db.Column(db.String(16), nullable=False, default='#c4883a')
    sort_order = db.Column(db.Integer,    nullable=False, default=0)
    created_at = db.Column(db.DateTime,   nullable=False, default=now_cst)

    tags = db.relationship('ProductTag', backref='category', lazy='dynamic')

    def to_dict(self) -> dict:
        return {
            'id':         self.id,
            'name':       self.name,
            'color':      self.color,
            'sort_order': self.sort_order,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


# 成品和标签的关联中间表
finished_tag = db.Table(
    'product_finished_tag',
    db.Column('finished_id', db.Integer, db.ForeignKey('product_finished.id'), primary_key=True),
    db.Column('tag_id',      db.Integer, db.ForeignKey('product_tag.id'),      primary_key=True),
)


class ProductTag(db.Model):
    __tablename__ = 'product_tag'

    id          = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    name        = db.Column(db.String(32),  nullable=False, unique=True)
    color       = db.Column(db.String(16),  nullable=True)   # 保留旧字段（兼容），分类颜色优先
    category_id = db.Column(db.Integer,     db.ForeignKey('product_tag_category.id'), nullable=True)
    created_at  = db.Column(db.DateTime,    nullable=False, default=now_cst)

    def to_dict(self) -> dict:
        # 颜色：优先取分类颜色，其次旧标签自身颜色，默认主色
        resolved_color = (
            self.category.color if self.category else
            (self.color if self.color else '#c4883a')
        )
        return {
            'id':          self.id,
            'name':        self.name,
            'color':       resolved_color,
            'category_id': self.category_id,
            'created_at':  self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }



finished_packaged = db.Table(
    'product_finished_packaged',
    db.Column('finished_id', db.Integer, db.ForeignKey('product_finished.id'), primary_key=True),
    db.Column('packaged_id', db.Integer, db.ForeignKey('product_packaged.id'), primary_key=True),
)

# status 常量
STATUS_UNRECORDED = 'unrecorded'  # 未录入
STATUS_RECORDED   = 'recorded'    # 已录入
STATUS_IGNORED    = 'ignored'     # 无需录入

VALID_STATUSES = {STATUS_UNRECORDED, STATUS_RECORDED, STATUS_IGNORED}

STATUS_LABELS = {
    STATUS_UNRECORDED: '未录入',
    STATUS_RECORDED:   '已录入',
    STATUS_IGNORED:    '无需录入',
}


class ProductFinished(db.Model):
    __tablename__ = 'product_finished'

    id            = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    code          = db.Column(db.String(64),  nullable=False, unique=True)
    status        = db.Column(db.String(20),  nullable=False, default=STATUS_UNRECORDED)
    model_id      = db.Column(db.Integer,     db.ForeignKey('product_model.id'), nullable=True)
    listed_yymm   = db.Column(db.String(7),   nullable=True)
    delisted_yymm = db.Column(db.String(7),   nullable=True)
    market        = db.Column(db.String(16),  nullable=True)   # domestic/foreign/both
    cover_image          = db.Column(db.String(500), nullable=True)
    cover_image_original = db.Column(db.String(500), nullable=True)   # 原始高清图 OSS URL
    img_updated_at       = db.Column(db.Integer,     nullable=True)   # 封面图更新时间戳（秒），用于缓存破坏
    created_at       = db.Column(db.DateTime,    nullable=False, default=now_cst)
    updated_at       = db.Column(db.DateTime,    nullable=False, default=now_cst, onupdate=now_cst)

    # 关联 product_model
    model = db.relationship('ProductModel', backref='finished_products', lazy='joined')

    # 关联 product_packaged（多对多）
    packaged_list = db.relationship(
        'ProductPackaged',
        secondary=finished_packaged,
        lazy='select',
        backref=db.backref('finished_list', lazy='select'),
    )

    # 关联 product_resource（多对多；排序查询请走 ResourceRepository.get_product_resources，不依赖此 relationship）
    resources = db.relationship(
        'ProductResource',
        secondary='product_finished_resource',
        lazy='select',
        backref=db.backref('finished_list', lazy='select'),
    )

    # 关联 product_tag（多对多）
    tags = db.relationship(
        'ProductTag',
        secondary=finished_tag,
        lazy='joined',
        backref=db.backref('finished_list', lazy='dynamic'),
    )

    def to_dict(self, with_packaged=False) -> dict:
        d = {
            'id':            self.id,
            'code':          self.code,
            'status':        self.status,
            'status_label':  STATUS_LABELS.get(self.status, self.status),
            'model_id':      self.model_id,
            'model_code':    self.model.model_code if self.model else None,
            'model_name':    self.model.name if self.model else None,
            'listed_yymm':   self.listed_yymm,
            'delisted_yymm': self.delisted_yymm,
            'market':        self.market,
            'cover_image':          self.cover_image,
            'cover_image_original': self.cover_image_original,
            'img_updated_at':       self.img_updated_at,
            'tags':          [t.to_dict() for t in self.tags],
            'created_at':    self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at':    self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None,
        }
        if with_packaged:
            d['packaged_list'] = [p.to_dict() for p in self.packaged_list]
        return d


class ProductPackaged(db.Model):
    __tablename__ = 'product_packaged'

    id           = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    code         = db.Column(db.String(64),  nullable=False, unique=True)
    name         = db.Column(db.String(255), nullable=False)
    length       = db.Column(db.Float,       nullable=True)
    width        = db.Column(db.Float,       nullable=True)
    height       = db.Column(db.Float,       nullable=True)
    volume       = db.Column(db.Float,       nullable=True)
    gross_weight = db.Column(db.Float,       nullable=True)
    net_weight   = db.Column(db.Float,       nullable=True)
    created_at   = db.Column(db.DateTime,    nullable=False, default=now_cst)
    updated_at   = db.Column(db.DateTime,    nullable=False, default=now_cst, onupdate=now_cst)

    def to_dict(self) -> dict:
        return {
            'id':           self.id,
            'code':         self.code,
            'name':         self.name,
            'length':       self.length,
            'width':        self.width,
            'height':       self.height,
            'volume':       self.volume,
            'gross_weight': self.gross_weight,
            'net_weight':   self.net_weight,
            'created_at':   self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at':   self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None,
        }


class PackagedEquivalent(db.Model):
    """产成品通用件：声明两个产成品在发货匹配时可互换"""
    __tablename__ = 'packaged_equivalent'
    __table_args__ = (
        db.UniqueConstraint('code_a', 'code_b', name='uq_equiv_pair'),
        db.Index('ix_equiv_code_a', 'code_a'),
        db.Index('ix_equiv_code_b', 'code_b'),
    )

    id         = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    code_a     = db.Column(db.String(64),  nullable=False)   # 字典序较小的编码
    code_b     = db.Column(db.String(64),  nullable=False)   # 字典序较大的编码
    note       = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime,    nullable=False, default=now_cst)

    def to_dict(self) -> dict:
        return {
            'id':         self.id,
            'code_a':     self.code_a,
            'code_b':     self.code_b,
            'note':       self.note,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }