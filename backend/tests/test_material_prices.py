"""物料库复用研发 BOM 成本价格的权限、惰性创建与性能测试。"""

import pytest
from flask import Flask, g
from sqlalchemy import event, text

from auth import generate_token, validate_csrf_request
from database.base import db
import database.models.product.category  # noqa: F401
import database.models.product.finished  # noqa: F401
import database.models.product.resource  # noqa: F401
from database.models.product.erp_code_rules import ErpCodeRule
from database.models.product.import_raw import ImportProductRaw
from database.models.product.material import (
    ErpGroupCategory, MaterialDisableKeyword, ProductMaterial,
)
from database.models.rd.cost import (
    CostBomLine, CostBomNode, CostMaterialPrice, CostMaterialRule,
    CostMaterialSupplier, CostSnapshot, CostSnapshotSku,
)
from database.repository.account import UserRepository
from routes.product.material import material_bp, material_cost_bp
from services.product.material import material_service
from services.product.material_price import material_price_service
from utils import now_cst


@pytest.fixture()
def price_app(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI='sqlite://', SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.before_request(validate_csrf_request)
    app.register_blueprint(material_bp, url_prefix='/api/material')
    app.register_blueprint(material_cost_bp, url_prefix='/api/material')
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 0))
    tables = [
        ImportProductRaw.__table__, ErpCodeRule.__table__, ErpGroupCategory.__table__,
        ProductMaterial.__table__, MaterialDisableKeyword.__table__,
        CostSnapshot.__table__, CostSnapshotSku.__table__, CostBomNode.__table__,
        CostBomLine.__table__, CostMaterialSupplier.__table__,
        CostMaterialPrice.__table__, CostMaterialRule.__table__,
    ]
    with app.app_context():
        db.metadata.create_all(bind=db.engine, tables=tables)
        db.session.execute(text('PRAGMA foreign_keys=ON'))
        material_service.invalidate_rule_cache()
        material_service.invalidate_disable_keyword_cache()
        material_service.invalidate_group_config_cache()
        yield app
        db.session.remove()
        db.metadata.drop_all(bind=db.engine, tables=list(reversed(tables)))


def _raw(code, group='G'):
    return ImportProductRaw(
        code=code, name=f'物料-{code}', spec='规格', status='生效',
        group_code=group, group_name='原材料_木器', imported_at=now_cst(),
    )


def _login(client, permissions):
    user = {
        'id': 1, 'username': 'tester', 'roles': [],
        'permissions': permissions, 'token_version': 0,
    }
    client.set_cookie('tmt_session', generate_token(user, csrf_token='csrf'))
    client.set_cookie('tmt_csrf', 'csrf')
    if hasattr(g, '_verified_session_user'):
        del g._verified_session_user


def test_lazy_node_creation_reuses_base_code_across_versions(price_app):
    with price_app.app_context():
        db.session.add_all([
            _raw('14WD11001-A01'), _raw('14WD11001-B01'),
            ErpGroupCategory(group_code='G', is_semi=True),
        ])
        db.session.commit()
        material_service.invalidate_group_config_cache()

        first = material_price_service.add_price(
            material_service.detail('14WD11001-A01').data,
            {'unit_price': '12.50', 'supplier_name': '供应商甲'}, 'tester',
        )
        second = material_price_service.add_price(
            material_service.detail('14WD11001-B01').data,
            {'unit_price': '13.00'}, 'tester',
        )

        assert first.success and second.success
        node = CostBomNode.query.one()
        assert node.code == '14WD11001'
        assert node.code_with_version == '14WD11001-A01'
        assert node.node_type == 'semi'
        assert CostMaterialPrice.query.count() == 2
        assert material_price_service.detail_fields(
            material_service.detail('14WD11001-B01').data
        )['cost_node_id'] == node.id


def test_material_price_fields_are_permission_gated_and_add_only_one_query(price_app):
    with price_app.app_context():
        db.session.add(_raw('ERP001-A01'))
        node = CostBomNode(
            code='ERP001', code_with_version='ERP001-A01', name='物料', node_type='material',
        )
        db.session.add(node)
        db.session.flush()
        db.session.add(CostMaterialPrice(
            node_id=node.id, unit_price=8.5, source='manual', created_by='tester',
        ))
        db.session.commit()
        material_service._rules()
        material_service._disable_keywords()
        material_service._group_configs()

        statements = []

        def capture(_conn, _cursor, statement, _params, _context, _many):
            if statement.lstrip().upper().startswith('SELECT'):
                statements.append(statement)

        event.listen(db.engine, 'before_cursor_execute', capture)
        try:
            plain = material_service.list_items(1, 20).data['items']
            plain_count = len(statements)
            statements.clear()
            priced = material_service.list_items(1, 20, include_cost=True).data['items']
            priced_count = len(statements)
        finally:
            event.remove(db.engine, 'before_cursor_execute', capture)

        assert 'latest_price' not in plain[0]
        assert priced[0]['latest_price'] == 8.5
        assert priced[0]['latest_price_source'] == 'manual'
        assert priced_count - plain_count == 1


def test_price_routes_enforce_rd_permissions_without_requiring_product_edit(price_app):
    with price_app.app_context():
        db.session.add(_raw('ERP001-A01'))
        db.session.commit()

    viewer = price_app.test_client()
    _login(viewer, ['product:view'])
    plain = viewer.get('/api/material/items').get_json()['data']['items'][0]
    assert 'latest_price' not in plain
    plain_detail = viewer.get('/api/material/items/ERP001-A01').get_json()['data']
    assert 'latest_price' not in plain_detail
    assert 'has_cost_node' not in plain_detail
    denied = viewer.post(
        '/api/material/items/ERP001-A01/prices', json={'unit_price': 10},
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert denied.status_code == 403

    rd_editor = price_app.test_client()
    _login(rd_editor, ['product:view', 'rd:view', 'rd:edit'])
    detail = rd_editor.get('/api/material/items/ERP001-A01').get_json()['data']
    assert detail['has_cost_node'] is False
    created = rd_editor.post(
        '/api/material/items/ERP001-A01/prices',
        json={'unit_price': 10, 'supplier_name': '供应商'},
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert created.status_code == 200, created.get_json()
    assert created.get_json()['data']['source'] == 'manual'
    price_id = created.get_json()['data']['id']

    listed = rd_editor.get('/api/material/items/ERP001-A01/prices')
    assert listed.status_code == 200
    assert listed.get_json()['data'][0]['supplier_name'] == '供应商'
    assert rd_editor.get('/api/material/items/ERP001-A01/usages').get_json()['data'] == []
    changed = rd_editor.patch(
        f'/api/material/prices/{price_id}', json={'supplier_name': '新供应商'},
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert changed.get_json()['data']['supplier_name'] == '新供应商'

    refreshed = rd_editor.get('/api/material/items/ERP001-A01').get_json()['data']
    assert refreshed['has_cost_node'] is True
    assert refreshed['latest_price'] == 10.0
    deleted = rd_editor.delete(
        f'/api/material/prices/{price_id}', headers={'X-CSRF-Token': 'csrf'},
    )
    assert deleted.status_code == 200


def test_price_state_filter_and_price_validation(price_app):
    with price_app.app_context():
        db.session.add_all([_raw('HAS-A01'), _raw('NONE-A01')])
        node = CostBomNode(code='HAS', code_with_version='HAS-A01', node_type='material')
        db.session.add(node)
        db.session.flush()
        db.session.add(CostMaterialPrice(node_id=node.id, unit_price=1, source='manual'))
        db.session.commit()

        has_items = material_service.list_items(
            1, 20, price_state='has', include_cost=True,
        ).data['items']
        none_items = material_service.list_items(
            1, 20, price_state='none', include_cost=True,
        ).data['items']
        assert [item['code'] for item in has_items] == ['HAS-A01']
        assert [item['code'] for item in none_items] == ['NONE-A01']

        invalid = material_price_service.add_price(
            material_service.detail('NONE-A01').data,
            {'unit_price': 0}, 'tester',
        )
        assert invalid.message.startswith('单价必须是大于 0')
        assert CostBomNode.query.filter_by(code='NONE').first() is None
        assert material_price_service.add_price(
            material_service.detail('NONE-A01').data, [], 'tester',
        ).message == '请求体格式无效'


def test_useless_material_cannot_create_price_or_empty_cost_node(price_app):
    with price_app.app_context():
        db.session.add_all([
            _raw('OLD001-A01', group='OLD'),
            # 多标签防御：只要包含 useless，即使同时是 material 也必须拒绝。
            ErpGroupCategory(group_code='OLD', is_material=True, is_useless=True),
        ])
        db.session.commit()
        material_service.invalidate_group_config_cache()
        material = material_service.detail('OLD001-A01').data
        assert material['categories'] == ['material', 'useless']
        assert material_price_service.detail_fields(material)['can_add_price'] is False

        result = material_price_service.add_price(
            material, {'unit_price': 9.9}, 'tester',
        )

        assert result.message == '无用物料不支持维护价格'
        assert CostBomNode.query.count() == 0
        assert CostMaterialPrice.query.count() == 0
