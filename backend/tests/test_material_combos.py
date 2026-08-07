"""售后物料组合的契约、权限和查询数量测试。"""

import pytest
from flask import Flask, g
from sqlalchemy import event, text
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from auth import generate_token, validate_csrf_request
from database.base import db
# 加载 ProductFinished 关系目标，避免独立测试应用配置 mapper 时缺少关联表。
import database.models.product.category  # noqa: F401
import database.models.product.finished  # noqa: F401
import database.models.product.resource  # noqa: F401
from database.models.product.import_raw import ImportProductRaw
from database.models.product.material import MaterialDisableKeyword, ProductMaterial
from database.models.product.material_combo import MaterialCombo, MaterialComboItem
from database.repository.account import UserRepository
from routes.product.material import material_bp
from services.product.material_combo import material_combo_service
from utils import now_cst


@pytest.fixture()
def combo_app(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI='sqlite://', SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.before_request(validate_csrf_request)
    app.register_blueprint(material_bp, url_prefix='/api/material')
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 0))
    tables = [
        ImportProductRaw.__table__, ProductMaterial.__table__,
        MaterialDisableKeyword.__table__,
        MaterialCombo.__table__, MaterialComboItem.__table__,
    ]
    with app.app_context():
        db.metadata.create_all(bind=db.engine, tables=tables)
        db.session.execute(text('PRAGMA foreign_keys=ON'))
        yield app
        db.session.remove()
        db.metadata.drop_all(bind=db.engine, tables=list(reversed(tables)))


def _payload(name='桌腿维修包', items=None):
    return {
        'name': name, 'category': '桌腿', 'remark': '常用组合',
        'is_disabled': False, 'sort_order': 0,
        'items': items if items is not None else [
            {'material_code': 'ERP001', 'quantity': 2, 'sort_order': 0},
            {'material_code': 'MISSING', 'quantity': 1, 'sort_order': 1},
        ],
    }


def _login(client, permissions):
    user = {
        'id': 1, 'username': 'tester', 'roles': [],
        'permissions': permissions, 'token_version': 0,
    }
    client.set_cookie('tmt_session', generate_token(user, csrf_token='csrf'))
    client.set_cookie('tmt_csrf', 'csrf')
    # fixture 为建表保留了 app_context；模拟真实请求间隔离认证缓存。
    if hasattr(g, '_verified_session_user'):
        del g._verified_session_user


def test_material_combo_join_key_declares_mysql_collation():
    ddl = str(CreateTable(MaterialComboItem.__table__).compile(dialect=mysql.dialect()))
    assert 'material_code VARCHAR(255) COLLATE utf8mb4_0900_ai_ci' in ddl


def test_combo_crud_replaces_items_and_preserves_missing_reference(combo_app):
    with combo_app.app_context():
        db.session.add_all([
            ImportProductRaw(
                code='ERP001', name='桌腿钢架', raw_name='桌腿钢架（已停用）',
                status='生效', group_code='14ME',
                group_name='原材料_金属件', imported_at=now_cst(),
            ),
            ProductMaterial(code='ERP001', short_name='桌腿'),
            MaterialDisableKeyword(keyword='停用', is_disabled=False),
        ])
        db.session.commit()

        created = material_combo_service.save(_payload(), created_by='tester')
        assert created.success
        combo_id = created.data['id']
        assert created.data['created_by'] == 'tester'
        assert created.data['items'][0] == {
            'id': created.data['items'][0]['id'], 'material_code': 'ERP001',
            'quantity': 2, 'sort_order': 0, 'material_name': '桌腿钢架',
            'short_name': '桌腿', 'group_name': '原材料_金属件',
            'is_missing': False, 'is_disabled': True,
        }
        assert created.data['items'][1]['is_missing'] is True
        assert created.data['items'][1]['material_name'] is None
        assert created.data['items'][1]['is_disabled'] is False

        updated = material_combo_service.save(
            _payload(items=[{'material_code': 'ERP001', 'quantity': 5}]),
            combo_id=combo_id,
        )
        assert updated.success
        assert [(row['material_code'], row['quantity']) for row in updated.data['items']] == [
            ('ERP001', 5),
        ]
        assert MaterialComboItem.query.filter_by(combo_id=combo_id).count() == 1

        assert material_combo_service.delete(combo_id).success
        assert MaterialComboItem.query.filter_by(combo_id=combo_id).count() == 0


def test_combo_validation_and_unique_name(combo_app):
    with combo_app.app_context():
        assert not material_combo_service.save(_payload(items=[
            {'material_code': 'A', 'quantity': 0},
        ])).success
        duplicate_items = material_combo_service.save(_payload(items=[
            {'material_code': 'A', 'quantity': 1},
            {'material_code': 'A', 'quantity': 2},
        ]))
        assert duplicate_items.message == '物料编码「A」重复'

        assert material_combo_service.save(_payload(name='同名组合', items=[])).success
        duplicate_name = material_combo_service.save(_payload(name='同名组合', items=[]))
        assert duplicate_name.message == '组合名称已存在'


def test_combo_list_uses_three_selects_and_returns_total(combo_app):
    with combo_app.app_context():
        db.session.add(ImportProductRaw(
            code='ERP001', name='物料', group_code='G', group_name='分组',
            imported_at=now_cst(),
        ))
        db.session.commit()
        assert material_combo_service.save(_payload(name='组合一')).success
        assert material_combo_service.save(_payload(name='组合二')).success
        statements = []

        def capture(_conn, _cursor, statement, _params, _context, _many):
            if statement.lstrip().upper().startswith('SELECT'):
                statements.append(statement)

        event.listen(db.engine, 'before_cursor_execute', capture)
        try:
            result = material_combo_service.list()
        finally:
            event.remove(db.engine, 'before_cursor_execute', capture)

        assert result.data['total'] == 2
        assert len(result.data['items']) == 2
        assert len(statements) == 3


def test_combo_routes_enforce_view_and_edit_permissions(combo_app):
    viewer = combo_app.test_client()
    _login(viewer, ['product:view'])
    assert viewer.get('/api/material/combos').status_code == 200
    denied = viewer.post(
        '/api/material/combos', json=_payload(items=[]),
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert denied.status_code == 403

    editor = combo_app.test_client()
    _login(editor, ['product:view', 'product:edit'])
    created = editor.post(
        '/api/material/combos', json=_payload(items=[]),
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert created.status_code == 200, created.get_json()
    assert created.get_json()['data']['name'] == '桌腿维修包'
