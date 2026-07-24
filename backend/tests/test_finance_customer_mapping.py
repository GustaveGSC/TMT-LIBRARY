from datetime import date
from pathlib import Path
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from database.models.shipping import (
    ShippingFinanceCustomerMapping,
    ShippingOperatorType,
    ShippingOrderFinished,
    ShippingRecord,
    ReturnRecord,
)
from database.models.product.erp_code_rules import ErpCodeRule
from database.models.product.finished import ProductTag, ProductTagCategory
import database.models.product.category  # noqa: F401 - resolve ORM relationships
import database.models.product.resource  # noqa: F401 - resolve ORM relationships
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
import routes.shipping as shipping_routes


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
        'status': 'export',
        'country': ' 印尼 ',
        'brand': ' Brand A ',
        'note': ' 人工确认 ',
    })

    assert result['customer_alias'] == '外贸-印尼-PT'
    assert captured['country'] == '印尼'
    assert captured['status'] == 'export'


@pytest.mark.parametrize('payload', [
    {'customer_alias': '', 'status': 'export'},
    {'customer_alias': '客户', 'status': 'excluded'},
    {'customer_alias': '客户', 'status': None},
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


def test_resolve_input_prefers_first_nonempty_customer_alias(monkeypatch):
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    from database.base import db
    db.init_app(app)
    records = [
        SimpleNamespace(
            ecommerce_order_no='ORDER-1', record_type='shipping', source='finance',
            shipped_date=date(2026, 7, 21), operator=None, channel_name=None,
            channel_code=None, channel_org_name=None, province=None, city=None,
            district=None, customer_alias=None, product_code='SKU-1', quantity=1,
        ),
        SimpleNamespace(
            ecommerce_order_no='ORDER-1', record_type='shipping', source='finance',
            shipped_date=date(2026, 7, 21), operator=None, channel_name=None,
            channel_code=None, channel_org_name=None, province=None, city=None,
            district=None, customer_alias='人工客户', product_code='SKU-2', quantity=1,
        ),
        SimpleNamespace(
            ecommerce_order_no='ORDER-1', record_type='shipping', source='finance',
            shipped_date=date(2026, 7, 21), operator=None, channel_name=None,
            channel_code=None, channel_org_name=None, province=None, city=None,
            district=None, customer_alias='不同简称', product_code='SKU-3', quantity=1,
        ),
    ]

    class FakeQuery:
        def filter(self, *_args):
            return self

        def all(self):
            return records

    with app.app_context():
        monkeypatch.setattr(ShippingRecord, 'query', FakeQuery())
        result = ShippingRepository.get_order_products(['ORDER-1'], source='finance')

    assert result['ORDER-1']['meta']['customer_alias'] == '人工客户'


def test_resolved_rows_persist_customer_alias(monkeypatch):
    saved = []
    monkeypatch.setattr(
        'database.repository.shipping.db.session.bulk_save_objects',
        lambda objects: saved.extend(objects),
    )

    ShippingRepository.bulk_insert_order_finished([{
        'ecommerce_order_no': 'ORDER-1',
        'customer_alias': '人工客户',
        'source': 'finance',
    }], commit_chunks=False)

    assert saved[0].customer_alias == '人工客户'
    assert ShippingOrderFinished.__table__.c.customer_alias.type.length == 255


def test_finance_chart_uses_manual_mapping_for_trade_country_brand_and_filters():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    from database.base import db
    db.init_app(app)

    with app.app_context():
        for model in (
            ProductTagCategory, ProductTag, ErpCodeRule, ShippingOperatorType,
            ShippingOrderFinished, ShippingFinanceCustomerMapping,
        ):
            model.__table__.create(db.engine)
        region = ProductTagCategory(name='地域', is_shipping_dim=True)
        brand = ProductTagCategory(name='品牌', is_shipping_dim=True)
        db.session.add_all([region, brand])
        db.session.flush()
        canada = ProductTag(name='加拿大', category_id=region.id)
        db.session.add(canada)
        db.session.add_all([
            ShippingFinanceCustomerMapping(
                customer_alias='EXPORT', status='export', country='加拿大', brand='品牌甲',
            ),
            ShippingFinanceCustomerMapping(
                customer_alias='THAILAND', status='export', country='泰国', brand='品牌泰',
            ),
            ShippingFinanceCustomerMapping(
                customer_alias='DOMESTIC', status='domestic', country='中国', brand='品牌乙',
            ),
            ShippingFinanceCustomerMapping(
                customer_alias='NON-SALES', status='non_sales', country='德国', brand='品牌丙',
            ),
            ShippingFinanceCustomerMapping(
                customer_alias='PENDING', status='pending', country='俄罗斯', brand='品牌丁',
            ),
            ShippingOrderFinished(
                ecommerce_order_no='E', finished_code='SKU-E', quantity=10,
                return_quantity=0, actual_quantity=10, source='finance',
                customer_alias='EXPORT', channel_name='外贸部',
            ),
            ShippingOrderFinished(
                ecommerce_order_no='D', finished_code='SKU-D', quantity=20,
                return_quantity=0, actual_quantity=20, source='finance',
                customer_alias='DOMESTIC', channel_name='内销部',
            ),
            ShippingOrderFinished(
                ecommerce_order_no='T', finished_code='SKU-T', quantity=15,
                return_quantity=0, actual_quantity=15, source='finance',
                customer_alias='THAILAND', channel_name='泰国渠道',
            ),
            ShippingOrderFinished(
                ecommerce_order_no='U', finished_code='SKU-U', quantity=30,
                return_quantity=0, actual_quantity=30, source='finance',
                customer_alias='UNMAPPED', channel_name='未映射部',
            ),
            ShippingOrderFinished(
                ecommerce_order_no='N', finished_code='SKU-N', quantity=40,
                return_quantity=0, actual_quantity=40, source='finance',
                customer_alias='NON-SALES', channel_name='非销售部',
            ),
            ShippingOrderFinished(
                ecommerce_order_no='P', finished_code='SKU-P', quantity=50,
                return_quantity=0, actual_quantity=50, source='finance',
                customer_alias='PENDING', channel_name='未审核部',
            ),
        ])
        db.session.commit()

        country = ShippingRepository.get_chart_data({
            'source': 'finance', 'group_by': f'tag:{region.id}', 'trade_type': 'all',
        })
        brand_rows = ShippingRepository.get_chart_data({
            'source': 'finance', 'group_by': f'tag:{brand.id}', 'trade_type': 'all',
        })
        domestic = ShippingRepository.get_chart_data({
            'source': 'finance', 'group_by': 'channel', 'trade_type': 'domestic',
        })
        foreign = ShippingRepository.get_chart_data({
            'source': 'finance', 'group_by': 'channel', 'trade_type': 'foreign',
        })
        all_rows = ShippingRepository.get_chart_data({
            'source': 'finance', 'group_by': 'channel', 'trade_type': 'all',
        })
        filtered = ShippingRepository.get_chart_data({
            'source': 'finance', 'group_by': 'channel', 'trade_type': 'all',
            'tag_filters': [{'category_id': region.id, 'tag_ids': [canada.id]}],
        })
        text_filtered_breakdown = ShippingRepository.get_chart_data({
            'source': 'finance', 'group_by': f'tag:{brand.id}', 'trade_type': 'foreign',
            'tag_filters': [{'category_id': region.id, 'tag_names': ['泰国']}],
        })

        assert {row['label'] for row in country['items']} == {'加拿大', '泰国'}
        assert {row['label'] for row in brand_rows['items']} == {'品牌甲', '品牌泰'}
        assert [row['label'] for row in domestic['items']] == ['内销部']
        assert {row['label'] for row in foreign['items']} == {'外贸部', '泰国渠道'}
        assert {row['label'] for row in all_rows['items']} == {
            '外贸部', '泰国渠道', '内销部', '未映射部', '非销售部', '未审核部',
        }
        assert [row['label'] for row in filtered['items']] == ['外贸部']
        assert text_filtered_breakdown['items'] == [{
            'label': '品牌泰', 'quantity': 15.0, 'return_quantity': 0.0,
            'actual_quantity': 15.0,
        }]

        # 修改人工映射后 chart-data 下一次查询实时 JOIN 新状态；
        # 不需要也不允许借助 resolve-all 刷新派生组合。
        ShippingRepository.save_finance_customer_mapping(
            'PENDING', 'export', country='俄罗斯', brand='品牌丁',
        )
        foreign_after_mapping = ShippingRepository.get_chart_data({
            'source': 'finance', 'group_by': 'channel', 'trade_type': 'foreign',
        })
        assert {row['label'] for row in foreign_after_mapping['items']} == {
            '外贸部', '泰国渠道', '未审核部',
        }


def test_finance_customer_mapping_api_contract_and_permissions(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(shipping_bp, url_prefix='/api/shipping')
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 0))
    monkeypatch.setattr(
        shipping_module.shipping_service, 'get_finance_customer_aliases',
        lambda keyword, status, page, per_page: {
            'items': [], 'total': 0, 'page': page, 'per_page': per_page,
            'keyword': keyword, 'status': status,
        },
    )
    monkeypatch.setattr(
        shipping_module.shipping_service, 'save_finance_customer_mapping',
        lambda payload: payload,
    )
    invalidations = []
    monkeypatch.setattr(
        shipping_routes,
        '_invalidate_chart_options_cache',
        lambda: invalidations.append(True),
    )
    monkeypatch.setattr(
        shipping_module.shipping_service,
        'resolve_all',
        lambda *_args, **_kwargs: pytest.fail('保存客户映射不应触发成品组合重算'),
    )
    client = app.test_client()
    view_user = {
        'id': 7, 'username': 'viewer', 'roles': [],
        'permissions': ['shipping:view'], 'token_version': 0,
    }
    client.set_cookie('tmt_session', generate_token(view_user, csrf_token='csrf'))

    response = client.get('/api/shipping/finance-customer-aliases?keyword=外贸&status=pending&page=2&per_page=20')
    assert response.status_code == 200
    assert response.get_json()['data']['keyword'] == '外贸'
    assert response.get_json()['data']['status'] == 'pending'
    assert client.get(
        '/api/shipping/finance-customer-aliases?status=excluded'
    ).status_code == 400
    assert client.post(
        '/api/shipping/finance-customer-aliases/mapping',
        json={'customer_alias': '客户', 'status': 'export'},
    ).status_code == 403

    edit_user = {**view_user, 'permissions': ['shipping:view', 'shipping:edit']}
    client.set_cookie('tmt_session', generate_token(edit_user, csrf_token='csrf'))
    response = client.post(
        '/api/shipping/finance-customer-aliases/mapping',
        json={'customer_alias': '客户', 'status': 'export'},
    )
    assert response.status_code == 200
    assert response.get_json()['data']['customer_alias'] == '客户'
    assert invalidations == [True]


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

    command.upgrade(config, '20260721_02')

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
        command.upgrade(config, '20260721_02')


def test_order_finished_alias_migration_adds_column_and_lookup_index(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'resolved-alias.db').as_posix()}"
    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(sa.text("""
            CREATE TABLE shipping_order_finished (
                id INTEGER PRIMARY KEY, source VARCHAR(20) NOT NULL
            )
        """))
    monkeypatch.setenv('DATABASE_URL', database_url)
    config = _migration_config(database_url)
    command.stamp(config, '20260721_02')

    command.upgrade(config, '20260721_03')

    inspector = sa.inspect(engine)
    assert 'customer_alias' in {
        column['name'] for column in inspector.get_columns('shipping_order_finished')
    }
    indexes = {
        index['name']: tuple(index['column_names'])
        for index in inspector.get_indexes('shipping_order_finished')
    }
    assert indexes['ix_sof_source_customer_alias'] == ('source', 'customer_alias')


def test_mapping_status_migration_preserves_review_decisions(tmp_path, monkeypatch):
    database_url = f"sqlite:///{(tmp_path / 'mapping-status.db').as_posix()}"
    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(sa.text("""
            CREATE TABLE shipping_finance_customer_mapping (
                id INTEGER PRIMARY KEY, customer_alias VARCHAR(255) NOT NULL,
                is_export BOOLEAN NOT NULL DEFAULT 0
            )
        """))
        connection.execute(sa.text("""
            INSERT INTO shipping_finance_customer_mapping
                (id, customer_alias, is_export)
            VALUES (1, '外贸客户', 1), (2, '赠品样品', 0)
        """))
    monkeypatch.setenv('DATABASE_URL', database_url)
    config = _migration_config(database_url)
    command.stamp(config, '20260721_03')

    command.upgrade(config, '20260721_04')

    inspector = sa.inspect(engine)
    columns = {column['name'] for column in inspector.get_columns(
        'shipping_finance_customer_mapping'
    )}
    assert 'status' in columns
    assert 'is_export' not in columns
    with engine.connect() as connection:
        rows = connection.execute(sa.text("""
            SELECT customer_alias, status
            FROM shipping_finance_customer_mapping ORDER BY id
        """)).all()
    assert rows == [('外贸客户', 'export'), ('赠品样品', 'non_sales')]
