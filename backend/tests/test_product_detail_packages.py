from flask import Flask

from database.base import db
# Load relationship targets before SQLAlchemy configures the package mappers.
from database.models.product.category import ProductCategory, ProductModel, ProductSeries
from database.models.product.detail_package import (
    ProductDetailPackage, ProductDetailPackageCleanupFailure,
    ProductDetailPackageMedia, package_model, package_tag,
)
from database.models.product.finished import ProductTag, ProductTagCategory
from services.product.detail_package import DetailPackageService
import services.product.detail_package as detail_package_service_module


class _Bucket:
    def __init__(self, fail_delete=False):
        self.fail_delete = fail_delete
        self.deleted = []

    def sign_url(self, method, key, expiry, headers=None):
        assert method == 'PUT'
        assert headers['Content-Type'].startswith(('image/', 'video/'))
        assert headers['Content-Length']
        return f'https://signed.example/{key}'

    def delete_object(self, key):
        if self.fail_delete:
            raise RuntimeError('OSS unavailable')
        self.deleted.append(key)


def _app():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI='sqlite://', SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    return app


def _create_tables():
    for table in (
        ProductCategory.__table__, ProductSeries.__table__, ProductModel.__table__,
        ProductTagCategory.__table__, ProductTag.__table__, ProductDetailPackage.__table__,
        package_tag, package_model, ProductDetailPackageMedia.__table__,
        ProductDetailPackageCleanupFailure.__table__,
    ):
        table.create(db.engine)


def test_package_media_presign_confirm_and_cleanup_failure_are_persisted(monkeypatch):
    app = _app()
    bucket = _Bucket(fail_delete=True)
    monkeypatch.setattr(detail_package_service_module, 'get_bucket', lambda: bucket)
    with app.app_context():
        _create_tables()
        service = DetailPackageService()
        created = service.create('客厅套装')
        assert created.success
        package_id = created.data['id']

        signed = service.presign_media(package_id, [{
            'ext': 'jpg', 'original_filename': 'cover.jpg', 'file_size': 12,
        }])
        assert signed.success
        item = signed.data['items'][0]
        assert item['storage_key'].startswith(f'tmt-library/product-detail/{package_id}/')

        confirmed = service.confirm_media(package_id, [{
            'storage_key': item['storage_key'], 'original_filename': 'cover.jpg', 'file_size': 12,
        }])
        assert confirmed.success
        media_id = confirmed.data[0]['id']
        assert service.delete_media(package_id, media_id).success
        assert db.session.get(ProductDetailPackageMedia, media_id) is None
        failure = ProductDetailPackageCleanupFailure.query.one()
        assert failure.package_id == package_id
        assert failure.storage_key == item['storage_key']


def test_confirm_rejects_foreign_or_nested_storage_key(monkeypatch):
    app = _app()
    monkeypatch.setattr(detail_package_service_module, 'get_bucket', _Bucket)
    with app.app_context():
        _create_tables()
        package_id = DetailPackageService().create('测试包').data['id']
        result = DetailPackageService().confirm_media(package_id, [{
            'storage_key': f'tmt-library/product-detail/{package_id}/nested/evil.jpg',
            'original_filename': 'evil.jpg', 'file_size': 1,
        }])
        assert not result.success
        assert ProductDetailPackageMedia.query.count() == 0
