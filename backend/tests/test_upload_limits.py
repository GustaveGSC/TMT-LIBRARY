import base64
import io
import zipfile

import openpyxl
import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

import app as app_module
from routes.product.finished import _decode_image_data_url
import routes.product.resource as resource_routes
import routes.version as version_routes
from upload_validation import (
    UploadValidationError,
    parse_declared_size,
    read_limited,
    read_spreadsheet_upload,
    validate_spreadsheet_bytes,
)


def _xlsx_bytes():
    workbook = openpyxl.Workbook()
    workbook.active.append(['code', 'name'])
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _image_data_url(actual_format='JPEG', declared_type='png'):
    output = io.BytesIO()
    Image.new('RGB', (2, 2), color='red').save(output, format=actual_format)
    encoded = base64.b64encode(output.getvalue()).decode()
    return f'data:image/{declared_type};base64,{encoded}'


def test_read_limited_rejects_before_consuming_unbounded_stream():
    with pytest.raises(UploadValidationError, match='不能超过'):
        read_limited(io.BytesIO(b'12345'), maximum=4, label='测试文件')


def test_valid_xlsx_passes_structure_checks():
    data = _xlsx_bytes()

    assert validate_spreadsheet_bytes(data, 'data.xlsx') == data


def test_forged_xlsx_extension_is_rejected():
    with pytest.raises(UploadValidationError, match='不是有效的 Excel'):
        validate_spreadsheet_bytes(b'not an excel workbook', 'data.xlsx')


def test_spreadsheet_mime_must_match_extension():
    upload = FileStorage(
        stream=io.BytesIO(_xlsx_bytes()),
        filename='data.xlsx',
        content_type='image/png',
    )

    with pytest.raises(UploadValidationError, match='MIME 类型与扩展名不一致'):
        read_spreadsheet_upload(upload, label='Excel 文件')


def test_xlsx_uncompressed_size_limit_blocks_zip_bomb_shape(monkeypatch):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', 'x')
        archive.writestr('xl/workbook.xml', 'x' * 200)
    monkeypatch.setattr('upload_validation.SPREADSHEET_UNCOMPRESSED_LIMIT', 100)

    with pytest.raises(UploadValidationError, match='解压后'):
        validate_spreadsheet_bytes(output.getvalue(), 'bomb.xlsx')


def test_image_with_forged_mime_is_rejected():
    with pytest.raises(UploadValidationError, match='MIME 类型与真实图片格式不一致'):
        _decode_image_data_url(
            _image_data_url(actual_format='JPEG', declared_type='png'),
            '封面图',
        )


def test_presign_size_must_be_positive_and_within_limit():
    assert parse_declared_size('1024', maximum=2048, label='资料文件') == 1024
    with pytest.raises(UploadValidationError, match='不能超过'):
        parse_declared_size(2049, maximum=2048, label='资料文件')
    with pytest.raises(UploadValidationError, match='必须大于'):
        parse_declared_size(0, maximum=2048, label='资料文件')


def test_resource_presign_binds_declared_content_length(monkeypatch):
    from flask import Flask

    captured = {}

    class Bucket:
        def sign_url(self, method, key, expiry, headers=None):
            captured.update(method=method, key=key, expiry=expiry, headers=headers)
            return 'https://signed.example/upload'

    monkeypatch.setattr(resource_routes, 'get_bucket', lambda: Bucket())
    app = Flask(__name__)
    with app.test_request_context(json={'ext': 'pdf', 'file_size': 1234}):
        response, status_code = resource_routes.presign_upload()

    assert status_code == 200
    assert captured['headers']['Content-Length'] == '1234'
    assert response.get_json()['data']['required_headers']['Content-Length'] == '1234'


def test_version_presign_rejects_missing_file_size():
    from flask import Flask

    app = Flask(__name__)
    with app.test_request_context(json={'filename': 'setup.exe'}):
        response, status_code = version_routes.presign_upload()

    assert status_code == 400
    assert response.get_json()['success'] is False


def test_global_request_limit_returns_standard_413(monkeypatch):
    from flask import has_app_context

    recovery_contexts = []
    monkeypatch.setenv('MAX_CONTENT_LENGTH', str(1024 * 1024))
    monkeypatch.setattr(app_module, 'validate_security_config', lambda: None)
    monkeypatch.setattr(app_module.db, 'init_app', lambda _app: None)
    monkeypatch.setattr(app_module, '_validate_database_revision', lambda _db: None)
    monkeypatch.setattr(
        'database.repository.shipping.shipping_repository.interrupt_running_tasks',
        lambda: recovery_contexts.append(has_app_context()) or 0,
    )
    monkeypatch.setattr(
        'database.repository.product.lifecycle.'
        'product_lifecycle_task_repository.interrupt_running_tasks',
        lambda: recovery_contexts.append(has_app_context()) or 0,
    )
    monkeypatch.setattr('threading.Thread.start', lambda _thread: None)
    application = app_module.create_app()

    @application.post('/test-body-limit')
    def test_body_limit():
        from flask import request
        request.get_data()
        return {'ok': True}

    response = application.test_client().post(
        '/test-body-limit',
        data=b'x' * (1024 * 1024 + 1),
        content_type='application/octet-stream',
    )

    assert response.status_code == 413
    assert response.get_json() == {
        'success': False,
        'message': '请求体不能超过 1MB',
    }
    assert recovery_contexts == [True, True]
