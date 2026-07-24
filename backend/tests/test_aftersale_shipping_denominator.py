from datetime import date

from flask import Flask
from sqlalchemy.dialects import mysql

from database.base import db
from database.models.aftersale import (
    AftersaleCase,
    AftersaleCaseReason,
    AftersaleReason,
    AftersaleReasonCategory,
)
from database.models.shipping import ShippingOperatorType, ShippingOrderFinished
from database.models.product.finished import ProductTag, ProductTagCategory  # noqa: F401
import database.models.product.category  # noqa: F401 - resolve ORM relationships
import database.models.product.resource  # noqa: F401 - resolve ORM relationships
from database.repository.aftersale import AftersaleRepository


def _app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app


def test_shipping_denominator_uses_shipping_source_and_excludes_aftersale_operators():
    app = _app()
    with app.app_context():
        ShippingOperatorType.__table__.create(db.engine)
        ShippingOrderFinished.__table__.create(db.engine)
        db.session.add(ShippingOperatorType(operator='售后人员', type='aftersale'))
        db.session.add_all([
            ShippingOrderFinished(
                ecommerce_order_no='S1', finished_code='F1',
                actual_quantity=10, source='shipping', operator='正常人员',
            ),
            ShippingOrderFinished(
                ecommerce_order_no='S2', finished_code='F1',
                actual_quantity=5, source='shipping', operator='售后人员',
            ),
            ShippingOrderFinished(
                ecommerce_order_no='F1', finished_code='F1',
                actual_quantity=100, source='finance', operator=None,
            ),
        ])
        db.session.commit()

        result = AftersaleRepository()._get_shipping_agg(
            {}, 'reason', {}, None, total_only=True,
        )

        assert result == 10


def test_shipping_denominator_compiles_with_source_date_index_hint():
    app = _app()
    with app.app_context():
        query = db.session.query(ShippingOrderFinished.id)
        scoped = AftersaleRepository._scope_shipping_denominator_query(
            query,
            ShippingOrderFinished,
            {'date_start': '2026-01-01'},
        )
        sql = str(scoped.statement.compile(dialect=mysql.dialect()))

        assert 'USE INDEX (ix_sof_source_date)' in sql
        assert 'shipping_order_finished.source = %s' in sql
        assert 'shipping_operator_type.type = %s' in sql


def test_reason_chart_reuses_one_shipping_denominator_query(monkeypatch):
    app = _app()
    with app.app_context():
        AftersaleReasonCategory.__table__.create(db.engine)
        AftersaleReason.__table__.create(db.engine)
        AftersaleCase.__table__.create(db.engine)
        AftersaleCaseReason.__table__.create(db.engine)

        category = AftersaleReasonCategory(name='结构')
        db.session.add(category)
        db.session.flush()
        reason = AftersaleReason(name='松动', category_id=category.id)
        case = AftersaleCase(
            ecommerce_order_no='A1',
            status='confirmed',
            shipped_date=date(2026, 1, 1),
        )
        db.session.add_all([reason, case])
        db.session.flush()
        db.session.add(AftersaleCaseReason(case_id=case.id, reason_id=reason.id))
        db.session.commit()

        repository = AftersaleRepository()
        calls = []

        def fake_shipping_agg(*_args, **_kwargs):
            calls.append(True)
            return 100

        monkeypatch.setattr(repository, '_get_shipping_agg', fake_shipping_agg)
        result = repository.get_chart_data({'group_by': 'reason'})

        assert len(calls) == 1
        assert result['items'][0]['shipped'] == 100
        assert result['summary']['overall_ratio'] == 1.0
