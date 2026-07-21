from datetime import date
from pathlib import Path
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from database.models.shipping import ShippingRecord, ReturnRecord
from database.repository.shipping import ShippingRepository
from services.shipping import (
    _REQUIRED_FINANCE_COL_NAMES,
    _build_col_map,
    _extract_finance_row,
    shipping_service,
)
import services.shipping as shipping_module
from auth import generate_token
from database.repository.account import UserRepository
from flask import Flask
from routes.shipping import shipping_bp


ROOT = Path(__file__).resolve().parents[2]


def test_finance_parser_reads_optional_customer_alias_and_stable_line_key():
    headers = ['平台订单', '交易日期', '部门名称', '品号', '数量', '省', '客户简称']
    col_map = _build_col_map(headers, required=_REQUIRED_FINANCE_COL_NAMES)

    parsed = _extract_finance_row(
        ('ORDER-1', '2026-07-21', '外贸部', 'SKU-1', '2', '浙江省', '外贸-印尼-PT'),
        col_map,
    )

    assert parsed['customer_alias'] == '外贸-印尼-PT'
    assert parsed['shipped_date'] == date(2026, 7, 21)
    assert parsed['line_no'] == 'F:20260721'
    assert '客户简称' not in _REQUIRED_FINANCE_COL_NAMES


def test_finance_parser_accepts_files_without_customer_alias():
    headers = ['平台订单', '交易日期', '部门名称', '品号', '数量', '省']
    parsed = _extract_finance_row(
        ('ORDER-1', '2026-07-21', '内销部', 'SKU-1', '2', '浙江省'),
        _build_col_map(headers, required=_REQUIRED_FINANCE_COL_NAMES),
    )

    assert parsed['customer_alias'] is None


@pytest.mark.parametrize(
    ('method_name', 'model', 'row'),
    [
        (
            'bulk_insert_shipping', ShippingRecord,
            {
                'ecommerce_order_no': 'ORDER-1', 'line_no': 'F:20260721',
                'product_code': 'SKU-1', 'shipped_date': date(2026, 7, 21),
                'customer_alias': '外贸-印尼-PT',
            },
        ),
        (
            'bulk_insert_return', ReturnRecord,
            {
                'ecommerce_order_no': 'ORDER-1', 'product_code': 'SKU-1',
                'shipped_date': date(2026, 7, 21), 'customer_alias': '外贸-印尼-PT',
            },
        ),
    ],
)
def test_bulk_writes_use_mysql_upsert_and_preserve_existing_alias_on_missing_value(
        monkeypatch, method_name, model, row):
    statements = []
    monkeypatch.setattr(
        'database.repository.shipping.db.session.execute',
        lambda statement, _params: statements.append(statement),
    )

    method = getattr(ShippingRepository, method_name)
    if method_name == 'bulk_insert_shipping':
        method(1, [row], source='finance', commit_chunks=False)
    else:
        method(1, [row], commit_chunks=False)

    sql = str(statements[0].compile(dialect=mysql.dialect()))
    assert 'ON DUPLICATE KEY UPDATE' in sql
    assert 'customer_alias = coalesce(' in sql.lower()
    assert 'IGNORE' not in sql
    assert model.__table__.c.customer_alias.type.length == 255


def test_mapping_service_validates_and_forwards_clean_values(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        'services.shipping.shipping_repository.save_finance_customer_mapping',
        lambda **kwargs: captured.update(kwargs) or kwargs,
    )

    result = shipping_service.save_finance_customer_mapping({
        'customer_alias': '  外贸-印尼-PT  ',
        'is_export': True,
        'country': ' 印尼 ',
        'brand': ' Brand A ',
        'note': ' 人工确认 ',
    })

    assert result['customer_alias'] == '外贸-印尼-PT'
    assert captured['country'] == '印尼'
    assert captured['is_export'] is True


@pytest.mark.parametrize('payload', [
    {'customer_alias': '', 'is_export': True},
    {'customer_alias': '客户', 'is_export': 'true'},
])
def test_mapping_service_rejects_invalid_payload(payload):
    with pytest.raises(ValueError):
        shipping_service.save_finance_customer_mapping(payload)


def test_finance_reimport_sends_existing_rows_through_upsert(monkeypatch):
    shipping_row = {
        'ecommerce_order_no': 'ORDER-1', 'product_code': 'SKU-1',
        'shipped_date': date(2026, 7, 21), 'customer_alias': '新简称',
    }
    return_row = dict(shipping_row)
    captured = {}
    repository = shipping_module.shipping_repository
    monkeypatch.setattr(
        shipping_module, '_parse_csv_finance_rows',
        lambda _content: ([shipping_row], [return_row], 0),
    )
    monkeypatch.setattr(shipping_module, '_merge_finance_shipping_rows', lambda rows: (rows, []))
    monkeypatch.setattr(shipping_module, '_merge_return_rows', lambda rows: (rows, []))
    monkeypatch.setattr(
        repository, 'get_existing_finance_keys',
        lambda _keys: {('ORDER-1', 'SKU-1', date(2026, 7, 21))},
    )
    monkeypatch.setattr(
        repository, 'get_existing_return_keys',
        lambda _keys: {('ORDER-1', 'SKU-1', date(2026, 7, 21))},
    )
    monkeypatch.setattr(repository, 'create_batch', lambda *_args: SimpleNamespace(id=9))
    monkeypatch.setattr(
        repository, 'bulk_insert_shipping',
        lambda _batch, rows, **_kwargs: captured.setdefault('shipping', rows) and len(rows),
    )
    monkeypatch.setattr(
        repository, 'bulk_insert_return',
        lambda _batch, rows, **_kwargs: captured.setdefault('returns', rows) and len(rows),
    )
    monkeypatch.setattr(repository, 'get_new_order_nos_by_source', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(shipping_module.db.session, 'commit', lambda: None)
    monkeypatch.setattr(shipping_module.db.session, 'rollback', lambda: None)

    result = shipping_service.import_finance('finance.csv', b'content')

    assert captured == {'shipping': [shipping_row], 'returns': [return_row]}
    assert result['inserted'] == 0
    assert result['updated'] == 1
    assert result['inserted_returns'] == 0
    assert result['updated_returns'] == 1


def test_finance_customer_mapping_api_contract_and_permissions(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(shipping_bp, url_prefix='/api/shipping')
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 0))
    monkeypatch.setattr(
        shipping_module.shipping_service, 'get_finance_customer_aliases',
        lambda keyword, page, per_page: {
            'items': [], 'total': 0, 'page': page, 'per_page': per_page,
            'keyword': keyword,
        },
    )
    monkeypatch.setattr(
        shipping_module.shipping_service, 'save_finance_customer_mapping',
        lambda payload: payload,
    )
    client = app.test_client()
    view_user = {
        'id': 7, 'username': 'viewer', 'roles': [],
        'permissions': ['shipping:view'], 'token_version': 0,
    }
    client.set_cookie('tmt_session', generate_token(view_user, csrf_token='csrf'))

    response = client.get('/api/shipping/finance-customer-aliases?keyword=外贸&page=2&per_page=20')
    assert response.status_code == 200
    assert response.get_json()['data']['keyword'] == '外贸'
    assert client.post(
        '/api/shipping/finance-customer-aliases/mapping',
        json={'customer_alias': '客户', 'is_export': True},
    ).status_code == 403

    edit_user = {**view_user, 'permissions': ['shipping:view', 'shipping:edit']}
    client.set_cookie('tmt_session', generate_token(edit_user, csrf_token='csrf'))
    response = client.post(
        '/api/shipping/finance-customer-aliases/mapping',
        json={'customer_alias': '客户', 'is_export': True},
    )
    assert response.status_code == 200
    assert response.get_json()['data']['customer_alias'] == '客户'


def _migration_config(database_url):
    config = Config(str(ROOT / 'alembic.ini'))
    config.set_main_option('sqlalchemy.url', database_url)
    return config


def _create_raw_tables(engine, *, duplicate=False):
    with engine.begin() as connection:
        connection.execute(sa.text("""
            CREATE TABLE shipping_record (
                id INTEGER PRIMARY KEY, source VARCHAR(20), ecommerce_order_no VARCHAR(100),
                product_code VARCHAR(100), shipped_date DATE, line_no VARCHAR(50)
            )
        """))
        connection.execute(sa.text("""
            CREATE TABLE return_record (
                id INTEGER PRIMARY KEY, ecommerce_order_no VARCHAR(100),
                product_code VARCHAR(100), shipped_date DATE
            )
        """))
        connection.execute(sa.text("""
            INSERT INTO shipping_record
                (id, source, ecommerce_order_no, product_code, shipped_date, line_no)
            VALUES (1, 'finance', 'ORDER-1', 'SKU-1', '2026-07-21', NULL)
        """))
        if duplicate:
            connection.execute(sa.text("""
                INSERT INTO shipping_record
                    (id, source, ecommerce_order_no, product_code, shipped_date, line_no)
                VALUES (2, 'finance', 'ORDER-1', 'SKU-1', '2026-07-21', NULL)
            """))


def test_customer_mapping_migration_adds_schema_and_normalizes_finance_key(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'mapping.db').as_posix()}"
    engine = sa.create_engine(database_url)
    _create_raw_tables(engine)
    monkeypatch.setenv('DATABASE_URL', database_url)
    config = _migration_config(database_url)
    command.stamp(config, '20260721_01')

    command.upgrade(config, 'head')

    inspector = sa.inspect(engine)
    assert 'shipping_finance_customer_mapping' in inspector.get_table_names()
    assert 'customer_alias' in {c['name'] for c in inspector.get_columns('shipping_record')}
    assert 'customer_alias' in {c['name'] for c in inspector.get_columns('return_record')}
    with engine.connect() as connection:
        assert connection.execute(sa.text(
            'SELECT line_no FROM shipping_record WHERE id = 1'
        )).scalar_one() == 'F:20260721'


def test_customer_mapping_migration_refuses_duplicate_finance_keys(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'duplicates.db').as_posix()}"
    engine = sa.create_engine(database_url)
    _create_raw_tables(engine, duplicate=True)
    monkeypatch.setenv('DATABASE_URL', database_url)
    config = _migration_config(database_url)
    command.stamp(config, '20260721_01')

    with pytest.raises(RuntimeError, match='重复财务发货键'):
        command.upgrade(config, 'head')
