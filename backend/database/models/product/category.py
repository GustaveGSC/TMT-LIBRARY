from datetime import datetime, timezone, timedelta
from database.base import db

CST = timezone(timedelta(hours=8))
def now_cst(): return datetime.now(CST).replace(tzinfo=None)


class ProductCategory(db.Model):
    __tablename__ = 'product_category'

    id         = db.Column(db.Integer,    primary_key=True, autoincrement=True)
    name       = db.Column(db.String(64), nullable=False, unique=True)
    sort_order = db.Column(db.Integer,    nullable=False, default=0)
    created_at = db.Column(db.DateTime,   nullable=False, default=now_cst)

    series = db.relationship('ProductSeries', backref='category', lazy='dynamic',
                             order_by='ProductSeries.sort_order')

    def to_dict(self, with_children=False) -> dict:
        d = {
            'id':         self.id,
            'name':       self.name,
            'sort_order': self.sort_order,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }
        if with_children:
            d['series'] = [s.to_dict(with_children=True) for s in self.series.order_by('sort_order')]
        return d


class ProductSeries(db.Model):
    __tablename__ = 'product_series'

    id          = db.Column(db.Integer,    primary_key=True, autoincrement=True)
    category_id = db.Column(db.Integer,    db.ForeignKey('product_category.id'), nullable=False)
    code        = db.Column(db.String(64), nullable=False)
    name        = db.Column(db.String(64), nullable=False)
    sort_order  = db.Column(db.Integer,    nullable=False, default=0)
    created_at  = db.Column(db.DateTime,   nullable=False, default=now_cst)

    __table_args__ = (
        db.UniqueConstraint('category_id', 'code', name='uq_series_code'),
        db.UniqueConstraint('category_id', 'name', name='uq_series_name'),
    )

    models = db.relationship('ProductModel', backref='series', lazy='dynamic',
                             order_by='ProductModel.sort_order')

    def to_dict(self, with_children=False) -> dict:
        d = {
            'id':          self.id,
            'category_id': self.category_id,
            'code':        self.code,
            'name':        self.name,
            'sort_order':  self.sort_order,
            'created_at':  self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }
        if with_children:
            d['models'] = [m.to_dict() for m in self.models.order_by('sort_order')]
        return d


class ProductModel(db.Model):
    __tablename__ = 'product_model'

    id         = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    series_id  = db.Column(db.Integer,     db.ForeignKey('product_series.id'), nullable=False)
    code       = db.Column(db.String(64),  nullable=False)
    name       = db.Column(db.String(64),  nullable=False)
    name_en    = db.Column(db.String(128), nullable=True)
    model_code = db.Column(db.String(64),  nullable=False, unique=True)
    sort_order = db.Column(db.Integer,     nullable=False, default=0)
    created_at = db.Column(db.DateTime,    nullable=False, default=now_cst)

    __table_args__ = (
        db.UniqueConstraint('series_id', 'code', name='uq_model_code'),
        db.UniqueConstraint('series_id', 'name', name='uq_model_name'),
    )

    def to_dict(self) -> dict:
        return {
            'id':         self.id,
            'series_id':  self.series_id,
            'code':       self.code,
            'name':       self.name,
            'name_en':    self.name_en,
            'model_code': self.model_code,
            'sort_order': self.sort_order,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }