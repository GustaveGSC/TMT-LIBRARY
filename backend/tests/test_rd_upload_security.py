import io
import os

from flask import Flask
from openpyxl import Workbook
import pytest

from auth import generate_token
from database.repository.account import UserRepository
from routes.rd import rd_bp
import routes.rd as rd_routes
from upload_validation import UploadValidationError


def _xlsx_bytes(rows):
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


@pytest.fixture
def rd_client(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(rd_bp, url_prefix='/api/rd')
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 0))
    user = {
        'id': 7, 'username': 'rd-user', 'roles': [],
        'permissions': ['rd:view', 'rd:edit'], 'token_version': 0,
    }
    client = app.test_client()
    client.set_cookie('tmt_session', generate_token(user, csrf_token='csrf'))
    client.set_cookie('tmt_csrf', 'csrf')
    return client


@pytest.mark.parametrize(('path', 'payload'), [
    ('/api/rd/ecr/parse-ecr', {'ecr_path': 'C:/secret.xlsx'}),
    ('/api/rd/ecr/compare-bom', {
        'bom_before_path': '/etc/passwd', 'bom_after_path': '/etc/shadow',
    }),
    ('/api/rd/pdm2bom/process', {'file_path': '/etc/passwd'}),
])
def test_legacy_server_path_payloads_are_rejected(rd_client, monkeypatch, path, payload):
    def forbidden_path_check(*_args, **_kwargs):
        raise AssertionError('不得检查客户端提交的服务端路径')

    monkeypatch.setattr(rd_routes.os.path, 'exists', forbidden_path_check)
    monkeypatch.setattr(rd_routes.os.path, 'isfile', forbidden_path_check)

    response = rd_client.post(
        path, json=payload, headers={'X-CSRF-Token': 'csrf'},
    )

    assert response.status_code == 400
    assert '上传' in response.get_json()['message']


@pytest.mark.parametrize('path', [
    '/api/rd/ecr/parse-ecr',
    '/api/rd/ecr/compare-bom',
    '/api/rd/pdm2bom/process',
])
def test_rd_upload_endpoints_reject_missing_files(rd_client, path):
    response = rd_client.post(
        path, data={}, headers={'X-CSRF-Token': 'csrf'},
    )

    assert response.status_code == 400
    assert '上传' in response.get_json()['message']


@pytest.mark.parametrize(('path', 'data'), [
    ('/api/rd/ecr/parse-ecr', {'ecr_file': (io.BytesIO(b'bad'), 'bad.xlsx')}),
    ('/api/rd/ecr/compare-bom', {
        'bom_before': (io.BytesIO(b'bad'), 'before.xlsx'),
        'bom_after': (io.BytesIO(b'bad'), 'after.xlsx'),
    }),
    ('/api/rd/pdm2bom/process', {'pdm_file': (io.BytesIO(b'bad'), 'bad.xlsx')}),
])
def test_rd_upload_endpoints_reject_invalid_file_content(rd_client, path, data):
    response = rd_client.post(
        path, data=data, headers={'X-CSRF-Token': 'csrf'},
    )

    assert response.status_code == 400


@pytest.mark.parametrize('path', [
    '/api/rd/ecr/parse-ecr',
    '/api/rd/ecr/compare-bom',
    '/api/rd/pdm2bom/process',
])
def test_rd_upload_endpoints_map_size_limit_to_413(rd_client, monkeypatch, path):
    monkeypatch.setattr(
        rd_routes, 'read_spreadsheet_upload',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            UploadValidationError('文件不能超过限制')
        ),
    )
    if path.endswith('parse-ecr'):
        data = {'ecr_file': (io.BytesIO(b'x'), 'x.xlsx')}
    elif path.endswith('compare-bom'):
        data = {
            'bom_before': (io.BytesIO(b'x'), 'before.xlsx'),
            'bom_after': (io.BytesIO(b'x'), 'after.xlsx'),
        }
    else:
        data = {'pdm_file': (io.BytesIO(b'x'), 'x.xlsx')}

    response = rd_client.post(
        path, data=data, headers={'X-CSRF-Token': 'csrf'},
    )

    assert response.status_code == 413


def test_rd_multipart_success_paths_cleanup_temp_files(rd_client, monkeypatch):
    removed = []
    real_unlink = os.unlink

    def tracked_unlink(path):
        removed.append(path)
        real_unlink(path)

    monkeypatch.setattr(rd_routes.os, 'unlink', tracked_unlink)
    monkeypatch.setattr(rd_routes, 'validate_bom', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        rd_routes, 'compare_bom_files',
        lambda *_args: {'changes': [], 'stats': {}},
    )
    generic_xlsx = _xlsx_bytes([['层次', '图号'], ['1', 'A']])
    pdm_xlsx = _xlsx_bytes([['品号', '层次'], ['A', '1']])

    parse_response = rd_client.post(
        '/api/rd/ecr/parse-ecr',
        data={'ecr_file': (io.BytesIO(generic_xlsx), 'ecr.xlsx')},
        headers={'X-CSRF-Token': 'csrf'},
    )
    compare_response = rd_client.post(
        '/api/rd/ecr/compare-bom',
        data={
            'bom_before': (io.BytesIO(generic_xlsx), 'before.xlsx'),
            'bom_after': (io.BytesIO(generic_xlsx), 'after.xlsx'),
        },
        headers={'X-CSRF-Token': 'csrf'},
    )
    pdm_response = rd_client.post(
        '/api/rd/pdm2bom/process',
        data={'pdm_file': (io.BytesIO(pdm_xlsx), 'pdm.xlsx')},
        headers={'X-CSRF-Token': 'csrf'},
    )

    assert parse_response.status_code == 200
    assert compare_response.status_code == 200
    assert pdm_response.status_code == 200
    assert len(removed) == 4
    assert all(not os.path.exists(path) for path in removed)
