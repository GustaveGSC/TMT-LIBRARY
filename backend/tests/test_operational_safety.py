import logging
from pathlib import Path
from types import SimpleNamespace

from flask import Flask
import pytest

import app as app_module
import error_handling


BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_internal_error_response_hides_exception_and_returns_trace_id(monkeypatch, caplog):
    flask_app = Flask(__name__)
    monkeypatch.setattr(error_handling.secrets, 'token_hex', lambda _length: 'abc123def456')

    with flask_app.test_request_context(), caplog.at_level(logging.ERROR):
        try:
            raise RuntimeError('mysql://secret@database/private-table')
        except RuntimeError:
            response, status = error_handling.internal_error_response(
                '测试数据库操作失败', '查询失败'
            )

    payload = response.get_json()
    assert status == 500
    assert payload == {
        'success': False,
        'message': '查询失败（错误编号：abc123def456）',
        'data': {'error_id': 'abc123def456'},
    }
    assert 'secret@database' not in payload['message']
    assert 'abc123def456' in caplog.text
    assert 'secret@database' in caplog.text


def test_database_readiness_executes_minimal_query():
    execution = SimpleNamespace(scalar_one=lambda: 1)

    class Session:
        def __init__(self):
            self.statement = None

        def execute(self, statement):
            self.statement = statement
            return execution

    session = Session()
    app_module._check_database_readiness(SimpleNamespace(session=session))

    assert str(session.statement) == 'SELECT 1'


def test_database_readiness_propagates_connection_failure():
    class Session:
        @staticmethod
        def execute(_statement):
            raise ConnectionError('database unavailable')

    with pytest.raises(ConnectionError, match='database unavailable'):
        app_module._check_database_readiness(SimpleNamespace(session=Session()))


def test_aftersale_filter_options_do_not_interpolate_column_names_into_sql():
    source = (
        BACKEND_DIR / 'database' / 'repository' / 'aftersale' / '__init__.py'
    ).read_text(encoding='utf-8')

    assert 'f"SELECT DISTINCT {col}' not in source
    assert 'q_distinct(AftersaleCase.channel_name)' in source
    assert 'q_distinct(AftersaleCase.district)' in source


def test_unsupported_product_delete_permission_is_removed_from_seed_and_migrated():
    seed = (BACKEND_DIR / 'seed_permissions.py').read_text(encoding='utf-8')
    migration = (
        BACKEND_DIR / 'migrations' / 'versions'
        / '20260721_01_remove_product_delete_permission.py'
    ).read_text(encoding='utf-8')

    assert 'product:delete' not in seed
    assert 'DELETE FROM role_permissions' in migration
    assert 'DELETE FROM permissions' in migration
