from flask import Flask
import pytest

from auth import generate_token
from database.base import db
from database.models.rd import EcrNote, EcrReminder
from database.repository.account import UserRepository
from routes.rd import rd_bp
from routes.rd.cost import cost_bp


RD_ROUTES = {
    ('POST', '/api/rd/ecr/export'),
    ('POST', '/api/rd/ecr/parse-ecr'),
    ('POST', '/api/rd/ecr/export-ecn'),
    ('POST', '/api/rd/ecr/compare-bom'),
    ('GET', '/api/rd/reminders'),
    ('GET', '/api/rd/reminders/all'),
    ('POST', '/api/rd/reminders'),
    ('PUT', '/api/rd/reminders/<int:rid>'),
    ('PUT', '/api/rd/reminders/<int:rid>/deactivate'),
    ('PUT', '/api/rd/reminders/<int:rid>/activate'),
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
    ('GET', '/api/rd/cost/suppliers'),
    ('POST', '/api/rd/cost/suppliers'),
    ('DELETE', '/api/rd/cost/suppliers/<int:supplier_id>'),
    ('PATCH', '/api/rd/cost/suppliers/<int:supplier_id>'),
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
    assert len(RD_ROUTES) == 17
    assert len(RD_COST_ROUTES) == 26

    note_modules = {
        app.view_functions[rule.endpoint].__module__
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith('/api/rd/notes')
    }
    assert note_modules == {'routes.rd.notes'}

    reminder_modules = {
        app.view_functions[rule.endpoint].__module__
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith('/api/rd/reminders')
    }
    assert reminder_modules == {'routes.rd.reminders'}


@pytest.fixture
def rd_app_client(monkeypatch):
    app = _app()
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 0))
    with app.app_context():
        EcrReminder.__table__.create(db.engine)
        EcrNote.__table__.create(db.engine)
    return app, app.test_client()


def test_reminders_require_rd_admin_for_management(rd_app_client):
    _app_obj, client = rd_app_client
    _set_user(client, username='viewer', permissions=['rd:view', 'rd:edit'])

    assert client.get('/api/rd/reminders').status_code == 200
    denied = client.get('/api/rd/reminders/all')
    assert denied.status_code == 400
    assert denied.get_json()['success'] is False
    denied_create = client.post(
        '/api/rd/reminders', json={'content': '越权创建'},
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert denied_create.status_code == 400
    assert denied_create.get_json()['message'] == '权限不足：需要研发部管理员权限'

    _set_user(
        client, username='rd-admin',
        permissions=['rd:view', 'rd:edit', 'rd:admin'],
    )
    created = client.post(
        '/api/rd/reminders', json={'content': '审核 BOM', 'created_by': 'rd-admin'},
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert created.status_code == 200
    reminder_id = created.get_json()['data']['id']

    all_items = client.get('/api/rd/reminders/all')
    assert all_items.status_code == 200
    assert [item['content'] for item in all_items.get_json()['data']] == ['审核 BOM']

    updated = client.put(
        f'/api/rd/reminders/{reminder_id}',
        json={'content': '复核 BOM', 'notes': '已更新'},
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert updated.status_code == 200
    assert updated.get_json()['data']['content'] == '复核 BOM'
    assert updated.get_json()['data']['notes'] == '已更新'

    deactivated = client.put(
        f'/api/rd/reminders/{reminder_id}/deactivate',
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert deactivated.status_code == 200
    assert deactivated.get_json()['data']['is_active'] is False
    assert client.get('/api/rd/reminders').get_json()['data'] == []

    activated = client.put(
        f'/api/rd/reminders/{reminder_id}/activate',
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert activated.status_code == 200
    assert activated.get_json()['data']['is_active'] is True
    assert [
        item['content'] for item in client.get('/api/rd/reminders').get_json()['data']
    ] == ['复核 BOM']


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
