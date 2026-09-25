from io import BytesIO

from flask import Flask
from openpyxl import Workbook
import pytest

from auth import generate_token
from database.base import db
from database.models.rd import EcrNote, MaterialGate
from database.models.product.material_supplier import MaterialSupplier
from database.models.rd.cost import (
    CostBomLine, CostBomNode, CostMaterialPrice, CostSnapshot, CostSnapshotSku,
)
from database.repository.account import UserRepository
from routes.rd import rd_bp
import routes.rd.cost as cost_routes
from routes.rd.cost import cost_bp


RD_ROUTES = {
    ('POST', '/api/rd/ecr/export'),
    ('POST', '/api/rd/ecr/parse-ecr'),
    ('POST', '/api/rd/ecr/export-ecn'),
    ('POST', '/api/rd/ecr/compare-bom'),
    ('GET', '/api/rd/material-gates'),
    ('GET', '/api/rd/material-gates/all'),
    ('POST', '/api/rd/material-gates'),
    ('PUT', '/api/rd/material-gates/<int:gate_id>'),
    ('PUT', '/api/rd/material-gates/<int:gate_id>/deactivate'),
    ('PUT', '/api/rd/material-gates/<int:gate_id>/activate'),
    ('POST', '/api/rd/material-gates/check'),
    ('POST', '/api/rd/material-gates/check-file'),
    ('GET', '/api/rd/notes'),
    ('POST', '/api/rd/notes'),
    ('PUT', '/api/rd/notes/<int:nid>'),
    ('DELETE', '/api/rd/notes/<int:nid>'),
    ('POST', '/api/rd/pdm2bom/process'),
    ('POST', '/api/rd/pdm2bom/export-erp'),
    ('POST', '/api/rd/pdm2bom/export-bom'),
}

RD_COST_ROUTES = {
    ('GET', '/api/rd/cost/snapshots'),
    ('POST', '/api/rd/cost/preview'),
    ('POST', '/api/rd/cost/import'),
    ('DELETE', '/api/rd/cost/snapshots/<int:snapshot_id>'),
    ('DELETE', '/api/rd/cost/skus/<int:sku_id>'),
    ('GET', '/api/rd/cost/snapshots/<int:snapshot_id>/skus'),
    ('GET', '/api/rd/cost/sku/<int:sku_id>/bom'),
    ('GET', '/api/rd/cost/nodes'),
    ('GET', '/api/rd/cost/nodes/<int:node_id>'),
    ('PATCH', '/api/rd/cost/nodes/<int:node_id>'),
    ('GET', '/api/rd/cost/nodes/<int:node_id>/price-history'),
    ('GET', '/api/rd/cost/nodes/<int:node_id>/usages'),
    ('GET', '/api/rd/cost/material-rules'),
    ('POST', '/api/rd/cost/material-rules'),
    ('DELETE', '/api/rd/cost/material-rules/<int:rule_id>'),
    ('GET', '/api/rd/cost/nodes/<int:node_id>/prices'),
    ('POST', '/api/rd/cost/nodes/<int:node_id>/prices'),
    ('PATCH', '/api/rd/cost/prices/<int:price_id>'),
    ('DELETE', '/api/rd/cost/prices/<int:price_id>'),
    ('GET', '/api/rd/cost/col-aliases'),
    ('PUT', '/api/rd/cost/col-aliases'),
    ('POST', '/api/rd/cost/estimate/calc'),
}


def _app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(rd_bp, url_prefix='/api/rd')
    app.register_blueprint(cost_bp, url_prefix='/api/rd/cost')
    return app


def _set_user(client, *, username, permissions):
    user = {
        'id': abs(hash(username)) % 100000 + 1,
        'username': username,
        'roles': [],
        'permissions': permissions,
        'token_version': 0,
    }
    client.set_cookie('tmt_session', generate_token(user, csrf_token='csrf'))
    client.set_cookie('tmt_csrf', 'csrf')


def test_rd_route_map_is_stable_before_module_split():
    app = _app()
    actual = {
        (method, rule.rule)
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith('/api/rd')
        for method in rule.methods - {'HEAD', 'OPTIONS'}
    }

    assert actual == RD_ROUTES | RD_COST_ROUTES
    assert len(RD_ROUTES) == 19
    assert len(RD_COST_ROUTES) == 22

    note_modules = {
        app.view_functions[rule.endpoint].__module__
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith('/api/rd/notes')
    }
    assert note_modules == {'routes.rd.notes'}

    gate_modules = {
        app.view_functions[rule.endpoint].__module__
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith('/api/rd/material-gates')
    }
    assert gate_modules == {'routes.rd.material_gate'}


@pytest.fixture
def rd_app_client(monkeypatch):
    app = _app()
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 0))
    monkeypatch.setattr(cost_routes, '_load_code_rules', lambda: [])
    with app.app_context():
        MaterialGate.__table__.create(db.engine)
        EcrNote.__table__.create(db.engine)
        CostSnapshot.__table__.create(db.engine)
        CostSnapshotSku.__table__.create(db.engine)
        CostBomNode.__table__.create(db.engine)
        CostBomLine.__table__.create(db.engine)
        MaterialSupplier.__table__.create(db.engine)
        CostMaterialPrice.__table__.create(db.engine)
    return app, app.test_client()


def test_rd_cost_requires_domain_permissions(rd_app_client):
    _app_obj, client = rd_app_client
    _set_user(client, username='other-user', permissions=['product:view'])
    assert client.get('/api/rd/cost/snapshots').status_code == 403

    _set_user(client, username='rd-viewer', permissions=['rd:view'])
    readable = client.get('/api/rd/cost/snapshots')
    assert readable.status_code == 200
    assert readable.get_json()['data'] == {'total': 0, 'items': []}
    assert client.post(
        '/api/rd/cost/preview',
        headers={'X-CSRF-Token': 'csrf'},
    ).status_code == 403

    _set_user(client, username='rd-editor', permissions=['rd:view', 'rd:edit'])
    editable = client.post(
        '/api/rd/cost/preview',
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert editable.status_code == 400
    assert editable.get_json()['message'] == '请上传 Excel 文件'


def test_cost_node_routes_remain_available_after_legacy_supplier_cleanup(
    rd_app_client,
):
    app, client = rd_app_client
    with app.app_context():
        node = CostBomNode(code='14WD01001', name='测试物料', node_type='material')
        snapshot = CostSnapshot(order_no='TEST-001')
        db.session.add_all([node, snapshot])
        db.session.flush()
        sku = CostSnapshotSku(
            snapshot_id=snapshot.id, finished_code='FINISHED-A',
            finished_name='测试成品',
        )
        db.session.add(sku)
        db.session.flush()
        db.session.add(CostBomLine(
            sku_id=sku.id, parent_node_id=node.id, child_node_id=node.id,
            quantity=2, unit_price=3,
        ))
        db.session.commit()
        node_id = node.id

    _set_user(client, username='rd-viewer', permissions=['rd:view'])
    listed = client.get('/api/rd/cost/nodes?q=14WD01001')
    detailed = client.get(f'/api/rd/cost/nodes/{node_id}')
    usages = client.get(f'/api/rd/cost/nodes/{node_id}/usages')

    assert listed.status_code == 200
    assert listed.get_json()['data']['items'][0]['code'] == '14WD01001'
    assert detailed.status_code == 200
    assert detailed.get_json()['data']['material_category'] is None
    assert 'suppliers' not in detailed.get_json()['data']
    assert usages.status_code == 200
    assert usages.get_json()['data'][0]['finished_code'] == 'FINISHED-A'

    assert client.get('/api/rd/cost/suppliers').status_code == 404


def test_material_gates_require_rd_admin_for_management(rd_app_client):
    _app_obj, client = rd_app_client
    _set_user(client, username='viewer', permissions=['rd:view', 'rd:edit'])

    assert client.get('/api/rd/material-gates').status_code == 200
    denied = client.get('/api/rd/material-gates/all')
    assert denied.status_code == 403
    assert denied.get_json()['success'] is False
    denied_create = client.post(
        '/api/rd/material-gates',
        json={'code': 'A001', 'level': 'warn', 'reason': '越权创建'},
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert denied_create.status_code == 403
    assert denied_create.get_json()['message'] == '权限不足：需要研发部管理员权限'

    _set_user(
        client, username='rd-admin',
        permissions=['rd:view', 'rd:edit', 'rd:admin'],
    )
    created = client.post(
        '/api/rd/material-gates',
        json={'code': 'A001', 'level': 'warn', 'reason': '审核 BOM'},
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert created.status_code == 200
    gate_id = created.get_json()['data']['id']
    assert created.get_json()['data']['created_by'] == 'rd-admin'

    all_items = client.get('/api/rd/material-gates/all')
    assert all_items.status_code == 200
    assert [item['reason'] for item in all_items.get_json()['data']] == ['审核 BOM']

    updated = client.put(
        f'/api/rd/material-gates/{gate_id}',
        json={'code': 'A001', 'level': 'block', 'reason': '复核 BOM'},
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert updated.status_code == 200
    assert updated.get_json()['data']['reason'] == '复核 BOM'
    assert updated.get_json()['data']['level'] == 'block'

    checked = client.post(
        '/api/rd/material-gates/check', json={'codes': ['A001', 'A001', 'MISSING']},
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert checked.status_code == 200
    assert checked.get_json()['data'] == {
        'warn': [], 'block': [{'code': 'A001', 'reason': '复核 BOM'}],
    }

    deactivated = client.put(
        f'/api/rd/material-gates/{gate_id}/deactivate',
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert deactivated.status_code == 200
    assert deactivated.get_json()['data']['is_active'] is False
    assert client.get('/api/rd/material-gates').get_json()['data'] == []

    activated = client.put(
        f'/api/rd/material-gates/{gate_id}/activate',
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert activated.status_code == 200
    assert activated.get_json()['data']['is_active'] is True
    assert [
        item['reason'] for item in client.get('/api/rd/material-gates').get_json()['data']
    ] == ['复核 BOM']


def test_material_gate_rejects_second_active_gate_for_same_code(rd_app_client):
    _app_obj, client = rd_app_client
    _set_user(
        client, username='rd-admin',
        permissions=['rd:view', 'rd:edit', 'rd:admin'],
    )
    headers = {'X-CSRF-Token': 'csrf'}
    first = client.post(
        '/api/rd/material-gates',
        json={'code': 'A001', 'level': 'warn', 'reason': '第一条'},
        headers=headers,
    )
    assert first.status_code == 200
    second = client.post(
        '/api/rd/material-gates',
        json={'code': 'A001', 'level': 'block', 'reason': '重复'},
        headers=headers,
    )
    assert second.status_code == 400
    assert second.get_json()['message'] == '该物料编码已有在架门禁，请先下架旧记录'


def test_material_gate_check_file_extracts_unique_codes(rd_app_client):
    _app_obj, client = rd_app_client
    _set_user(
        client, username='rd-admin',
        permissions=['rd:view', 'rd:edit', 'rd:admin'],
    )
    headers = {'X-CSRF-Token': 'csrf'}
    client.post(
        '/api/rd/material-gates',
        json={'code': 'A001', 'level': 'warn', 'reason': '核查材料'},
        headers=headers,
    )

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(['品号', '名称'])
    sheet.append(['A001', '命中'])
    sheet.append(['A001', '重复'])
    sheet.append(['B002', '未命中'])
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    checked = client.post(
        '/api/rd/material-gates/check-file',
        data={'file': (buffer, 'materials.xlsx')},
        content_type='multipart/form-data',
        headers=headers,
    )
    assert checked.status_code == 200
    assert checked.get_json()['data'] == {
        'scanned_count': 2,
        'warn': [{'code': 'A001', 'reason': '核查材料'}],
        'block': [],
    }


def test_pdm_process_returns_sorted_unique_material_codes(rd_app_client):
    _app_obj, client = rd_app_client
    _set_user(client, username='rd-editor', permissions=['rd:view', 'rd:edit'])

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(['品号', '层次'])
    sheet.append(['B002', '1'])
    sheet.append(['A001', '1.1'])
    sheet.append(['B002', '1.2'])
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    response = client.post(
        '/api/rd/pdm2bom/process',
        data={'pdm_file': (buffer, 'pdm.xlsx')},
        content_type='multipart/form-data',
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert response.status_code == 200
    assert response.get_json()['data']['material_codes'] == ['A001', 'B002']


def test_notes_are_isolated_by_authenticated_username(rd_app_client):
    _app_obj, client = rd_app_client
    permissions = ['rd:view', 'rd:edit']
    _set_user(client, username='alice', permissions=permissions)
    created = client.post(
        '/api/rd/notes', json={'content': 'Alice 私有笔记'},
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert created.status_code == 200
    note_id = created.get_json()['data']['id']

    blank = client.post(
        '/api/rd/notes', json={'content': '   '},
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert blank.status_code == 400
    assert blank.get_json()['message'] == '笔记内容不能为空'

    _set_user(client, username='bob', permissions=permissions)
    assert client.get('/api/rd/notes').get_json()['data'] == []
    denied_update = client.put(
        f'/api/rd/notes/{note_id}', json={'content': '越权修改'},
        headers={'X-CSRF-Token': 'csrf'},
    )
    denied_delete = client.delete(
        f'/api/rd/notes/{note_id}', headers={'X-CSRF-Token': 'csrf'},
    )
    assert denied_update.status_code == 400
    assert denied_delete.status_code == 400

    _set_user(client, username='alice', permissions=permissions)
    updated = client.put(
        f'/api/rd/notes/{note_id}', json={'content': 'Alice 更新后笔记'},
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert updated.status_code == 200
    assert updated.get_json()['data']['content'] == 'Alice 更新后笔记'
    assert client.delete(
        f'/api/rd/notes/{note_id}', headers={'X-CSRF-Token': 'csrf'},
    ).status_code == 200
    assert client.get('/api/rd/notes').get_json()['data'] == []
