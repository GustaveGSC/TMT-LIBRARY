from flask import Flask
from sqlalchemy import event

from database.base import db
from database.models.product.category import (
    ProductCategory,
    ProductModel,
    ProductSeries,
)
from services.product.category import category_service


def _app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app


def test_category_tree_contract_uses_three_queries_regardless_of_node_count():
    app = _app()
    with app.app_context():
        ProductCategory.__table__.create(db.engine)
        ProductSeries.__table__.create(db.engine)
        ProductModel.__table__.create(db.engine)

        category = ProductCategory(name='两平米', sort_order=2)
        other_category = ProductCategory(name='其他', sort_order=1)
        db.session.add_all([category, other_category])
        db.session.flush()
        first_series = ProductSeries(
            category_id=category.id, code='B', name='系列B', sort_order=2,
        )
        second_series = ProductSeries(
            category_id=category.id, code='A', name='系列A', sort_order=1,
        )
        db.session.add_all([first_series, second_series])
        db.session.flush()
        db.session.add_all([
            ProductModel(
                series_id=first_series.id, code='B2', name='型号B2',
                model_code='B2', sort_order=2,
            ),
            ProductModel(
                series_id=first_series.id, code='B1', name='型号B1',
                model_code='B1', sort_order=1,
            ),
        ])
        db.session.commit()

        statements = []

        def count_statement(_conn, _cursor, statement, _params, _context, _many):
            if statement.lstrip().upper().startswith('SELECT'):
                statements.append(statement)

        event.listen(db.engine, 'before_cursor_execute', count_statement)
        try:
            result = category_service.get_tree()
        finally:
            event.remove(db.engine, 'before_cursor_execute', count_statement)

        assert len(statements) == 3
        assert [item['name'] for item in result.data] == ['其他', '两平米']
        assert result.data[0]['series'] == []
        series = result.data[1]['series']
        assert [item['name'] for item in series] == ['系列A', '系列B']
        assert series[0]['models'] == []
        assert [item['name'] for item in series[1]['models']] == ['型号B1', '型号B2']
