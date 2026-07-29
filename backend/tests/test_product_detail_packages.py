from flask import Flask

from database.base import db
# Load relationship targets before SQLAlchemy configures the package mappers.
from database.models.product.category import ProductCategory, ProductModel, ProductSeries
from database.models.product.detail_package import (
    ProductDetailPackage, ProductDetailPackageCleanupFailure,
    ProductDetailPackageMedia, package_category, package_model, package_series, package_tag,
)
from database.models.product.finished import ProductFinished, ProductTag, ProductTagCategory, finished_tag
from database.repository.product.detail_package import DetailPackageRepository
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
        ProductFinished.__table__, finished_tag, package_tag, package_model, package_series, package_category,
        ProductDetailPackageMedia.__table__,
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


def test_get_one_returns_complete_package_and_its_media():
    app = _app()
    with app.app_context():
        _create_tables()
        package = ProductDetailPackage(name='已有媒体的包')
        db.session.add(package)
        db.session.flush()
        db.session.add_all([
            ProductDetailPackageMedia(
                package_id=package.id, file_type='image', original_filename='a.jpg',
                oss_url='https://oss.example/a.jpg', storage_key='tmt-library/product-detail/1/a.jpg',
                file_size=10, sort_order=2,
            ),
            ProductDetailPackageMedia(
                package_id=package.id, file_type='video', original_filename='b.mp4',
                oss_url='https://oss.example/b.mp4', storage_key='tmt-library/product-detail/1/b.mp4',
                file_size=20, sort_order=1,
            ),
        ])
        db.session.commit()

        result = DetailPackageService().get_one(package.id)

        assert result.success
        assert result.data['name'] == '已有媒体的包'
        assert [item['original_filename'] for item in result.data['media']] == ['b.mp4', 'a.jpg']
        assert result.data['media'][0]['file_type'] == 'video'
        assert not DetailPackageService().get_one(999).success


def test_series_and_category_scopes_match_existing_and_future_models():
    app = _app()
    with app.app_context():
        _create_tables()
        category = ProductCategory(name='品类')
        db.session.add(category)
        db.session.flush()
        series = ProductSeries(category_id=category.id, code='SER-A', name='系列A')
        other_series = ProductSeries(category_id=category.id, code='SER-B', name='系列B')
        db.session.add_all([series, other_series])
        db.session.flush()
        model = ProductModel(series_id=series.id, code='MOD-A', name='型号A', model_code='M-A')
        db.session.add(model)
        db.session.flush()
        finished = ProductFinished(code='FIN-A', model_id=model.id)
        series_package = ProductDetailPackage(name='系列范围包')
        category_package = ProductDetailPackage(name='品类范围包')
        db.session.add_all([finished, series_package, category_package])
        db.session.commit()

        assert DetailPackageService().set_series(series_package.id, [series.id]).success
        assert DetailPackageService().set_categories(category_package.id, [category.id]).success
        package = DetailPackageRepository.get(series_package.id)
        assert package.to_dict()['series_ids'] == [series.id]
        assert DetailPackageRepository.get(category_package.id).to_dict()['category_ids'] == [category.id]

        _finished, matches = DetailPackageRepository.matching_finished_packages('FIN-A')
        assert {package.name for package, _media in matches} == {'系列范围包', '品类范围包'}

        # Subsequent models/finished products match through their hierarchy; no model-id snapshot is stored.
        future_model = ProductModel(series_id=series.id, code='MOD-FUTURE', name='未来型号', model_code='M-F')
        category_model = ProductModel(series_id=other_series.id, code='MOD-CAT', name='品类新增型号', model_code='M-C')
        db.session.add_all([future_model, category_model])
        db.session.flush()
        db.session.add_all([
            ProductFinished(code='FIN-FUTURE', model_id=future_model.id),
            ProductFinished(code='FIN-CATEGORY', model_id=category_model.id),
        ])
        db.session.commit()

        _finished, future_matches = DetailPackageRepository.matching_finished_packages('FIN-FUTURE')
        _finished, category_matches = DetailPackageRepository.matching_finished_packages('FIN-CATEGORY')
        assert {package.name for package, _media in future_matches} == {'系列范围包', '品类范围包'}
        assert {package.name for package, _media in category_matches} == {'品类范围包'}
