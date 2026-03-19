from datetime import datetime, timezone, timedelta
from database.base import db

CST = timezone(timedelta(hours=8))
def now_cst(): return datetime.now(CST).replace(tzinfo=None)

# 成品和标签的关联中间表
finished_tag = db.Table(
    'product_finished_tag',
    db.Column('finished_id', db.Integer, db.ForeignKey('product_finished.id'), primary_key=True),
    db.Column('tag_id',      db.Integer, db.ForeignKey('product_tag.id'),      primary_key=True),
)


class ProductTag(db.Model):
    __tablename__ = 'product_tag'

    id         = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    name       = db.Column(db.String(32),  nullable=False, unique=True)
    color      = db.Column(db.String(16),  nullable=False, default='#c4883a')
    created_at = db.Column(db.DateTime,    nullable=False, default=now_cst)

    def to_dict(self) -> dict:
        return {
            'id':         self.id,
            'name':       self.name,
            'color':      self.color,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
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
    cover_image   = db.Column(db.String(500), nullable=True)
    created_at    = db.Column(db.DateTime,    nullable=False, default=now_cst)
    updated_at    = db.Column(db.DateTime,    nullable=False, default=now_cst, onupdate=now_cst)

    # 关联 product_model
    model = db.relationship('ProductModel', backref='finished_products', lazy='joined')

    # 关联 product_packaged（多对多）
    packaged_list = db.relationship(
        'ProductPackaged',
        secondary=finished_packaged,
        lazy='dynamic',
        backref=db.backref('finished_list', lazy='dynamic'),
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
            'cover_image':   self.cover_image,
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
    length       = db.Column(db.Integer,     nullable=True)
    width        = db.Column(db.Integer,     nullable=True)
    height       = db.Column(db.Integer,     nullable=True)
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