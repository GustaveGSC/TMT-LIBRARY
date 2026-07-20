from decimal import Decimal

from flask import Flask

from routes.shipping import shipping_bp
from services import shipping as shipping_module


def test_independent_return_import_route_is_removed():
    app = Flask(__name__)
    app.register_blueprint(shipping_bp, url_prefix='/api/shipping')

    routes = {
        (rule.rule, ','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'})))
        for rule in app.url_map.iter_rules()
    }

    assert ('/api/shipping/import/finance', 'POST') in routes
    assert ('/api/shipping/import/return', 'POST') not in routes


def test_independent_return_import_service_is_removed():
    assert not hasattr(shipping_module.shipping_service, 'import_return')


def test_finance_csv_splits_positive_and_negative_quantities():
    csv_bytes = (
        '平台订单,订单单号,交易日期,部门名称,品号,数量,省,市,区\n'
        'ORDER-1,,2026-07-01,电商部,SKU-A,2,浙江省,杭州市,余杭区\n'
        ',PREFIX-ORDER-2,2026-07-02,电商部,SKU-B,-3,北京市,北京市,朝阳区\n'
        'ORDER-3,,2026-07-03,售后组,SKU-C,1,上海市,上海市,浦东新区\n'
        'ORDER-4,,2026-07-04,电商部,SKU-D,0,广东省,深圳市,南山区\n'
    ).encode('utf-8')

    shipping_rows, return_rows, aftersale_count = (
        shipping_module._parse_csv_finance_rows(csv_bytes)
    )

    assert [row['ecommerce_order_no'] for row in shipping_rows] == ['ORDER-1']
    assert shipping_rows[0]['quantity'] == Decimal('2')
    assert [row['ecommerce_order_no'] for row in return_rows] == ['ORDER-2']
    assert return_rows[0]['quantity'] == Decimal('3')
    assert return_rows[0]['city'] == '北京市'
    assert aftersale_count == 1
