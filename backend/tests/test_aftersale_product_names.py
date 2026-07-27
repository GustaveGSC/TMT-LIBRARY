from decimal import Decimal
from datetime import datetime

import sqlalchemy as sa
from flask import Flask

from database.base import db
from database.models.product.import_raw import ImportProductRaw
from database.models.shipping import ShippingBatch, ShippingRecord
from database.repository.aftersale import AftersaleRepository


def test_aftersale_products_prefer_import_raw_name_in_constant_queries():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI='sqlite://', SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    with app.app_context():
        for model in (ShippingBatch, ShippingRecord, ImportProductRaw):
            model.__table__.create(db.engine)
        batch = ShippingBatch(filename='test.xlsx', type='shipping', imported_at=datetime.now())
        db.session.add(batch)
        db.session.flush()
        db.session.add_all([
            ImportProductRaw(
                code='SKU-FULL', name='完整规格名称', group_code='G', group_name='组',
                imported_at=datetime.now(),
            ),
            ShippingRecord(
                batch_id=batch.id, record_type='shipping', source='shipping',
                ecommerce_order_no='ORDER-1', line_no='1', product_code='SKU-FULL',
                product_name='导入短名称', quantity=Decimal('2'),
            ),
            ShippingRecord(
                batch_id=batch.id, record_type='shipping', source='shipping',
                ecommerce_order_no='ORDER-2', line_no='1', product_code='SKU-MISSING',
                product_name='原始兜底名称', quantity=Decimal('3'),
            ),
        ])
        db.session.commit()

        statements = []

        def collect_sql(_connection, _cursor, statement, _parameters, _context, _executemany):
            statements.append(statement)

        sa.event.listen(db.engine, 'before_cursor_execute', collect_sql)
        try:
            products = AftersaleRepository()._get_batch_order_products(['ORDER-1', 'ORDER-2'])
        finally:
            sa.event.remove(db.engine, 'before_cursor_execute', collect_sql)

        assert products['ORDER-1'][0]['name'] == '完整规格名称'
        assert products['ORDER-2'][0]['name'] == '原始兜底名称'
        assert sum('shipping_record' in sql.lower() for sql in statements) == 1
        assert sum('import_product_raw' in sql.lower() for sql in statements) == 1
