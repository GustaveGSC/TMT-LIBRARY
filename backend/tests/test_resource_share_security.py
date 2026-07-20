import io
import time

from flask import Flask

from routes.product import resource as resource_routes


class _Object:
    def read(self):
        return b'image-bytes'


class _Bucket:
    def get_object(self, _storage_key):
        return _Object()


class _ResourceResult:
    success = True
    data = {
        'title': '示例图片',
        'file_type': 'image',
        'storage_key': 'tmt-library/resources/example.png',
    }


def _app():
    app = Flask(__name__)
    app.register_blueprint(resource_routes.resource_bp, url_prefix='/api/resources')
    return app


def test_og_image_rejects_missing_share_token(monkeypatch):
    get_resource_called = False

    def get_resource(_resource_id):
        nonlocal get_resource_called
        get_resource_called = True
        return _ResourceResult()

    monkeypatch.setattr(resource_routes.resource_service, 'get_resource', get_resource)

    response = _app().test_client().get('/api/resources/7/og-image')

    assert response.status_code == 403
    assert get_resource_called is False


def test_og_image_accepts_valid_share_token(monkeypatch):
    monkeypatch.setattr(resource_routes.resource_service, 'get_resource', lambda _id: _ResourceResult())
    monkeypatch.setattr(resource_routes, 'get_bucket', lambda: _Bucket())
    exp = int(time.time()) + 60
    key = resource_routes._make_share_token(7, exp)

    response = _app().test_client().get(
        f'/api/resources/7/og-image?key={key}&exp={exp}'
    )

    assert response.status_code == 200
    assert response.data == b'image-bytes'
    assert response.content_type.startswith('image/png')


def test_share_page_includes_token_in_og_image_url(monkeypatch):
    monkeypatch.setattr(resource_routes.resource_service, 'get_resource', lambda _id: _ResourceResult())
    monkeypatch.setattr(
        resource_routes,
        'get_bucket',
        lambda: type('Bucket', (), {'sign_url': lambda *_args, **_kwargs: 'https://example.test/image.png'})(),
    )
    exp = int(time.time()) + 60
    key = resource_routes._make_share_token(7, exp)

    response = _app().test_client().get(
        f'/api/resources/7/share-page?key={key}&exp={exp}'
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert f'/api/resources/7/og-image?key={key}&exp={exp}' in html
