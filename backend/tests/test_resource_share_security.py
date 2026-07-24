import io
import time
from pathlib import Path

from flask import Flask
from markupsafe import escape

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
    backend_root = Path(__file__).resolve().parents[1]
    app = Flask(
        __name__,
        template_folder=str(backend_root / 'templates'),
        static_folder=str(backend_root / 'static'),
    )
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
    assert f'/api/resources/7/og-image?key={key}&amp;exp={exp}' in html


def test_share_page_escapes_untrusted_title_in_html_and_attributes(monkeypatch):
    malicious_title = '\"><script>alert(\"xss\")</script>&'
    result = _ResourceResult()
    result.data = {
        'title': malicious_title,
        'file_type': 'image',
        'storage_key': 'tmt-library/resources/example.png',
    }
    monkeypatch.setattr(resource_routes.resource_service, 'get_resource', lambda _id: result)
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
    assert malicious_title not in html
    assert str(escape(malicious_title)) in html
    assert '<script>alert(' not in html
    assert "script-src 'self' https://registry.npmmirror.com" in response.headers['Content-Security-Policy']


def test_pdf_share_page_keeps_filename_out_of_executable_javascript(monkeypatch):
    malicious_filename = 'x</a><script>alert(1)</script>.pdf'
    result = _ResourceResult()
    result.data = {
        'title': 'PDF',
        'file_type': 'pdf',
        'original_filename': malicious_filename,
        'storage_key': 'tmt-library/resources/example.pdf',
    }
    monkeypatch.setattr(resource_routes.resource_service, 'get_resource', lambda _id: result)
    monkeypatch.setattr(
        resource_routes,
        'get_bucket',
        lambda: type('Bucket', (), {'sign_url': lambda *_args, **_kwargs: 'https://example.test/file.pdf'})(),
    )
    exp = int(time.time()) + 60
    key = resource_routes._make_share_token(7, exp)

    response = _app().test_client().get(
        f'/api/resources/7/share-page?key={key}&exp={exp}'
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert malicious_filename not in html
    assert str(escape(malicious_filename)) in html
    assert '<script>alert(1)</script>' not in html
    assert 'resource-share-pdf.js' in html
    assert 'innerHTML' not in html


def test_external_share_redirect_rejects_non_http_scheme(monkeypatch):
    result = _ResourceResult()
    result.data = {
        'title': '危险链接',
        'file_type': 'link',
        'storage_key': None,
        'url': 'javascript:alert(document.domain)',
    }
    monkeypatch.setattr(resource_routes.resource_service, 'get_resource', lambda _id: result)
    exp = int(time.time()) + 60
    key = resource_routes._make_share_token(7, exp)

    response = _app().test_client().get(
        f'/api/resources/7/share-page?key={key}&exp={exp}'
    )

    assert response.status_code == 400
    assert 'javascript:' not in response.get_data(as_text=True)
