from flask import Flask

from database.base import db
from database.models.aftersale import (
    AftersaleCaseMedia, AftersaleMediaCleanupFailure, AftersaleMediaUploadSession,
)
from database.models.account import User
from services.aftersale import AftersaleService
import services.aftersale as aftersale_service_module


class _Bucket:
    def __init__(self, fail_delete=False):
        self.deleted = []
        self.fail_delete = fail_delete

    def sign_url(self, method, key, expiry, headers=None):
        assert method == 'PUT'
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
    for model in (User, AftersaleCaseMedia, AftersaleMediaUploadSession, AftersaleMediaCleanupFailure):
        model.__table__.create(db.engine)


def test_media_session_is_server_manifest_and_replace_cleans_after_commit(monkeypatch):
    app = _app()
    bucket = _Bucket()
    monkeypatch.setattr(aftersale_service_module, 'get_bucket', lambda: bucket)
    with app.app_context():
        _create_tables()
        service = AftersaleService()
        first = service.presign_media({
            'order_no': 'ORDER_1', 'mode': 'append',
            'files': [{'ext': 'jpg', 'file_size': 12, 'original_filename': 'a.jpg'}],
        }, 1)
        assert first.success
        # confirm ignores hostile client-provided metadata: it only needs the opaque token.
        assert service.confirm_media({
            'session_token': first.data['session_token'],
            'uploaded': [{'storage_key': 'tmt-library/other/evil.jpg', 'file_size': 1}],
        }, 1).success
        old_key = AftersaleCaseMedia.query.one().storage_key

        replacement = service.presign_media({
            'order_no': 'ORDER_1', 'mode': 'replace',
            'files': [{'ext': 'mp4', 'file_size': 20, 'original_filename': 'b.mp4'}],
        }, 1)
        assert replacement.success
        confirmed = service.confirm_media({'session_token': replacement.data['session_token']}, 1)
        assert confirmed.success
        assert [row.seq for row in AftersaleCaseMedia.query.all()] == [1]
        assert old_key in bucket.deleted
        assert service.confirm_media({'session_token': replacement.data['session_token']}, 1).data['idempotent']


def test_media_sequence_reservations_and_cleanup_failure_are_persisted(monkeypatch):
    app = _app()
    bucket = _Bucket(fail_delete=True)
    monkeypatch.setattr(aftersale_service_module, 'get_bucket', lambda: bucket)
    with app.app_context():
        _create_tables()
        service = AftersaleService()
        first = service.presign_media({
            'order_no': 'ORDER-2', 'mode': 'append',
            'files': [{'ext': 'png', 'file_size': 10, 'original_filename': 'a.png'}],
        }, 1)
        second = service.presign_media({
            'order_no': 'ORDER-2', 'mode': 'append',
            'files': [{'ext': 'webp', 'file_size': 10, 'original_filename': 'b.webp'}],
        }, 1)
        assert [item['seq'] for item in first.data['items']] == [1]
        assert [item['seq'] for item in second.data['items']] == [2]
        assert service.confirm_media({'session_token': first.data['session_token']}, 1).success
        replacement = service.presign_media({
            'order_no': 'ORDER-2', 'mode': 'replace',
            'files': [{'ext': 'jpg', 'file_size': 10, 'original_filename': 'c.jpg'}],
        }, 1)
        assert service.confirm_media({'session_token': replacement.data['session_token']}, 1).success
        assert AftersaleMediaCleanupFailure.query.count() == 1
        assert service.precheck_media({'order_nos': ['ORDER-2']}).data['ORDER-2']['count'] == 1
        assert service.get_media_flags({'order_nos': ['ORDER-2']}).data == {'ORDER-2': 1}


def test_media_rejects_path_like_order_or_filename(monkeypatch):
    app = _app()
    monkeypatch.setattr(aftersale_service_module, 'get_bucket', _Bucket)
    with app.app_context():
        _create_tables()
        service = AftersaleService()
        assert not service.presign_media({
            'order_no': '../bad', 'mode': 'append', 'files': [],
        }, 1).success
        assert not service.presign_media({
            'order_no': 'SAFE', 'mode': 'append',
            'files': [{'ext': 'jpg', 'file_size': 1, 'original_filename': '../bad.jpg'}],
        }, 1).success
