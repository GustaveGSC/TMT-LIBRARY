from database.base import db
from utils import now_cst


package_tag = db.Table(
    'product_detail_package_tag',
    db.Column('package_id', db.Integer, db.ForeignKey('product_detail_package.id', ondelete='CASCADE'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('product_tag.id', ondelete='CASCADE'), primary_key=True),
)

package_model = db.Table(
    'product_detail_package_model',
    db.Column('package_id', db.Integer, db.ForeignKey('product_detail_package.id', ondelete='CASCADE'), primary_key=True),
    db.Column('model_id', db.Integer, db.ForeignKey('product_model.id', ondelete='CASCADE'), primary_key=True),
)

package_series = db.Table(
    'product_detail_package_series',
    db.Column('package_id', db.Integer, db.ForeignKey('product_detail_package.id', ondelete='CASCADE'), primary_key=True),
    db.Column('series_id', db.Integer, db.ForeignKey('product_series.id', ondelete='CASCADE'), primary_key=True),
)

package_category = db.Table(
    'product_detail_package_category',
    db.Column('package_id', db.Integer, db.ForeignKey('product_detail_package.id', ondelete='CASCADE'), primary_key=True),
    db.Column('category_id', db.Integer, db.ForeignKey('product_category.id', ondelete='CASCADE'), primary_key=True),
)


class ProductDetailPackage(db.Model):
    __tablename__ = 'product_detail_package'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(200), nullable=False)
    tag_condition = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now_cst)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_cst, onupdate=now_cst)

    tags = db.relationship('ProductTag', secondary=package_tag, lazy='selectin')
    models = db.relationship('ProductModel', secondary=package_model, lazy='selectin')
    series = db.relationship('ProductSeries', secondary=package_series, lazy='selectin')
    categories = db.relationship('ProductCategory', secondary=package_category, lazy='selectin')

    def to_dict(self, *, media=None, media_count=None, cover_thumbnail=None):
        result = {
            'id': self.id, 'name': self.name,
            'tag_ids': [tag.id for tag in self.tags],
            'tag_condition': self.tag_condition,
            'model_ids': [model.id for model in self.models],
            'series_ids': [series.id for series in self.series],
            'category_ids': [category.id for category in self.categories],
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None,
        }
        if media is not None:
            result['media'] = [item.to_dict() for item in media]
        if media_count is not None:
            result['media_count'] = media_count
        if cover_thumbnail is not None:
            result['cover_thumbnail'] = cover_thumbnail
        return result


class ProductDetailPackageMedia(db.Model):
    __tablename__ = 'product_detail_package_media'
    __table_args__ = (
        db.UniqueConstraint('storage_key', name='uq_product_detail_package_media_storage_key'),
        db.Index('ix_product_detail_package_media_package_id', 'package_id'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    package_id = db.Column(db.Integer, db.ForeignKey('product_detail_package.id', ondelete='CASCADE'), nullable=False)
    file_type = db.Column(db.String(20), nullable=False)
    original_filename = db.Column(db.String(300), nullable=False)
    oss_url = db.Column(db.String(1000), nullable=False)
    storage_key = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.BigInteger, nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=now_cst)

    def to_dict(self):
        return {
            'id': self.id, 'file_type': self.file_type,
            'original_filename': self.original_filename, 'oss_url': self.oss_url,
            'storage_key': self.storage_key, 'file_size': self.file_size,
            'sort_order': self.sort_order,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


class ProductDetailPackageCleanupFailure(db.Model):
    """Records OSS objects that could not be deleted after DB deletion.

    The media/package deletion remains successful once its database transaction has
    committed.  Keeping this record makes the otherwise asynchronous OSS cleanup
    failure observable and recoverable.
    """

    __tablename__ = 'product_detail_package_cleanup_failure'
    __table_args__ = (
        db.Index('ix_product_detail_package_cleanup_failure_created_at', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    package_id = db.Column(db.Integer, nullable=True)
    storage_key = db.Column(db.String(500), nullable=False)
    error_message = db.Column(db.String(1000), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now_cst)
