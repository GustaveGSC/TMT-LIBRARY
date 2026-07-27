import os
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from flask import Flask
from sqlalchemy.dialects import mysql

from database.base import db
from database.models.shipping import (
    ReturnRecord, ReturnWarehouseFilter, ShippingBatch, ShippingOrderFinished,
    ShippingRecord, ShippingTask,
)
import database.repository.shipping as shipping_repository_module
from database.repository.shipping import ShippingRepository
from utils import now_cst


def _app(tmp_path):
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f'sqlite:///{tmp_path / "scoped-stale.db"}',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    with app.app_context():
        for table in (
            ShippingTask.__table__, ShippingBatch.__table__, ShippingRecord.__table__,
            ReturnRecord.__table__, ReturnWarehouseFilter.__table__,
            ShippingOrderFinished.__table__,
        ):
            table.create(db.engine)
    return app


def _batch():
    batch = ShippingBatch(type='shipping', filename='fixture.xlsx', imported_at=now_cst())
    db.session.add(batch)
    db.session.flush()
    return batch


def _finished(order_no, source='shipping', code='F-1'):
    row = ShippingOrderFinished(
        ecommerce_order_no=order_no, source=source, finished_code=code,
        is_stale=False,
    )
    db.session.add(row)
    return row


def test_component_scope_marks_existing_raw_and_return_pairs_only(tmp_path):
    app = _app(tmp_path)
    with app.app_context():
        batch = _batch()
        _finished('raw-hit', code='F-1')
        _finished('return-hit', source='finance', code='F-2')
        _finished('unrelated', code='F-3')
        db.session.add_all([
            ShippingRecord(
                batch_id=batch.id, ecommerce_order_no='raw-hit', source='shipping',
                record_type='shipping', product_code='P-1', quantity=1,
            ),
            ReturnRecord(
                batch_id=batch.id, ecommerce_order_no='return-hit',
                product_code='P-1', quantity=-1,
            ),
            # No derived row: this must not inflate the scope count.
            ShippingRecord(
                batch_id=batch.id, ecommerce_order_no='not-derived', source='shipping',
                record_type='shipping', product_code='P-1', quantity=1,
            ),
        ])
        db.session.commit()

        assert ShippingRepository.mark_stale_for_component_codes({'P-1'}, set()) == 2
        db.session.commit()

        states = {row.ecommerce_order_no: row.is_stale for row in ShippingOrderFinished.query.all()}
        assert states == {'raw-hit': True, 'return-hit': True, 'unrelated': False}

        # Exercise the three-branch union shape too: two component branches
        # are empty, while the finished-code branch supplies the one target.
        ShippingOrderFinished.query.update({ShippingOrderFinished.is_stale: False})
        db.session.commit()
        assert ShippingRepository.mark_stale_for_component_codes(
            {'not-present'}, {'F-3'},
        ) == 1


def test_warehouse_scope_marks_both_sources_for_a_changed_return_warehouse(tmp_path):
    app = _app(tmp_path)
    with app.app_context():
        batch = _batch()
        _finished('shared', 'shipping')
        _finished('shared', 'finance')
        _finished('other', 'shipping')
        db.session.add_all([
            ReturnRecord(
                batch_id=batch.id, ecommerce_order_no='shared', product_code='P-1',
                warehouse_name='退货仓', quantity=-1,
            ),
            ReturnRecord(
                batch_id=batch.id, ecommerce_order_no='other', product_code='P-2',
                warehouse_name='其他仓', quantity=-1,
            ),
        ])
        db.session.commit()

        assert ShippingRepository.mark_stale_for_warehouse_names({'退货仓'}) == 2
        db.session.commit()

        states = {
            (row.source, row.ecommerce_order_no): row.is_stale
            for row in ShippingOrderFinished.query.all()
        }
        assert states == {
            ('shipping', 'shared'): True,
            ('finance', 'shared'): True,
            ('shipping', 'other'): False,
        }


def test_mysql_order_join_compiles_with_explicit_legacy_collation(monkeypatch):
    """Protect the production-only 1267 collation failure from regressing."""
    fake_db = SimpleNamespace(
        session=SimpleNamespace(
            get_bind=lambda: SimpleNamespace(dialect=mysql.dialect()),
        ),
    )
    monkeypatch.setattr(shipping_repository_module, 'db', fake_db)

    expression = shipping_repository_module._order_no_join(
        ReturnRecord.ecommerce_order_no,
        ShippingOrderFinished.ecommerce_order_no,
    )
    sql = str(expression.compile(dialect=mysql.dialect()))
    assert 'COLLATE utf8mb4_unicode_ci' in sql


@pytest.mark.mysql_integration
@pytest.mark.skipif(
    not os.getenv('MYSQL_COLLATION_TEST_DATABASE_URL'),
    reason='requires an isolated MySQL database with the production collations',
)
def test_mysql_collation_join_executes_on_real_mysql():
    """Read-only staging gate; execute the exact problematic comparison on MySQL."""
    engine = sa.create_engine(os.environ['MYSQL_COLLATION_TEST_DATABASE_URL'])
    statement = sa.select(ShippingOrderFinished.id).join(
        ReturnRecord,
        ReturnRecord.ecommerce_order_no.collate('utf8mb4_unicode_ci')
        == ShippingOrderFinished.ecommerce_order_no,
    ).limit(1)
    with engine.connect() as connection:
        connection.execute(sa.text('SET SESSION TRANSACTION READ ONLY'))
        connection.execute(statement).all()


@pytest.mark.mysql_integration
@pytest.mark.skipif(
    not os.getenv('MYSQL_COLLATION_TEST_DATABASE_URL'),
    reason='requires an isolated MySQL database with the production collations',
)
def test_mysql_component_scope_union_executes_on_real_mysql():
    """Run the former AttributeError path against MySQL, read-only."""
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=os.environ['MYSQL_COLLATION_TEST_DATABASE_URL'],
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    with app.app_context():
        db.session.execute(sa.text('SET SESSION TRANSACTION READ ONLY'))
        # Deliberately absent codes still execute all three UNION branches;
        # read-only mode proves this gate cannot mutate its fixture database.
        assert ShippingRepository.mark_stale_for_component_codes(
            {'__mysql_scope_missing_component__'},
            {'__mysql_scope_missing_finished__'},
        ) == 0
        db.session.rollback()
