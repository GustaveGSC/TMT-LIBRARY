from flask import Flask
from sqlalchemy import event

from database.base import db
from database.models.product.erp_code_rules import ErpCodeRule
from database.models.shipping import ShippingOperatorType, ShippingOrderFinished
from database.repository.shipping import ShippingRepository


def _app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app


def test_ordinary_chart_dimension_derives_summary_without_second_fact_scan():
    app = _app()
    with app.app_context():
        ErpCodeRule.__table__.create(db.engine)
        ShippingOperatorType.__table__.create(db.engine)
        ShippingOrderFinished.__table__.create(db.engine)
        db.session.add_all([
            ShippingOrderFinished(
                ecommerce_order_no='A', finished_code='F1', channel_name='直营',
                quantity=12, return_quantity=2, actual_quantity=10,
                source='shipping',
            ),
            ShippingOrderFinished(
                ecommerce_order_no='B', finished_code='F2', channel_name='经销',
                quantity=7, return_quantity=1, actual_quantity=6,
                source='shipping',
            ),
        ])
        db.session.commit()

        fact_selects = []

        def capture_fact_select(_conn, _cursor, statement, _params, _context, _many):
            normalized = statement.lower()
            if (
                normalized.lstrip().startswith('select')
                and 'shipping_order_finished' in normalized
            ):
                fact_selects.append(statement)

        event.listen(db.engine, 'before_cursor_execute', capture_fact_select)
        try:
            result = ShippingRepository.get_chart_data({
                'group_by': 'channel',
                'source': 'shipping',
            })
        finally:
            event.remove(db.engine, 'before_cursor_execute', capture_fact_select)

        assert len(fact_selects) == 1
        assert result['summary'] == {
            'quantity': 19.0,
            'return_quantity': 3.0,
            'actual_quantity': 16.0,
        }
        assert sum(item['actual_quantity'] for item in result['items']) == 16.0
