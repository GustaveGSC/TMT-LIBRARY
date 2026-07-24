from flask import Flask

from auth import generate_token
from database.repository.account import UserRepository
from database.repository.shipping import shipping_repository
from routes.shipping import shipping_bp
from services.shipping import shipping_service


def _set_user(client, *, username, permissions):
    payload = {
        'id': abs(hash(username)) % 100000 + 1,
        'username': username,
        'roles': [],
        'permissions': permissions,
        'token_version': 0,
    }
    client.set_cookie('tmt_session', generate_token(payload, csrf_token='csrf'))
    client.set_cookie('tmt_csrf', 'csrf')


def test_warehouse_filter_requires_shipping_edit_with_cookie_jwt(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(shipping_bp, url_prefix='/api/shipping')
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 0))
    saved = []
    monkeypatch.setattr(
        shipping_service,
        'save_warehouse_filters',
        lambda items: saved.append(items) or {'updated': len(items)},
    )
    client = app.test_client()
    payload = [{'warehouse_name': '测试仓', 'is_excluded': True}]

    _set_user(client, username='viewer', permissions=['shipping:view'])
    denied = client.post(
        '/api/shipping/warehouses/filter',
        json=payload,
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert denied.status_code == 403
    assert saved == []

    _set_user(
        client,
        username='editor',
        permissions=['shipping:view', 'shipping:edit'],
    )
    allowed = client.post(
        '/api/shipping/warehouses/filter',
        json=payload,
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert allowed.status_code == 200
    assert allowed.get_json()['success'] is True
    assert allowed.get_json()['data'] == {'updated': 1}
    assert saved == [payload]


def test_chart_data_remains_query_post_for_shipping_viewer(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(shipping_bp, url_prefix='/api/shipping')
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 0))
    monkeypatch.setattr(
        shipping_service,
        'get_chart_data',
        lambda _params: {'summary': {}, 'items': []},
    )
    client = app.test_client()
    _set_user(client, username='viewer', permissions=['shipping:view'])

    response = client.post(
        '/api/shipping/chart-data',
        json={'group_by': 'date'},
        headers={'X-CSRF-Token': 'csrf'},
    )

    assert response.status_code == 200


def test_task_cancel_requires_edit_and_old_path_uses_same_contract(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(shipping_bp, url_prefix='/api/shipping')
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 0))
    calls = []

    def request_cancel(task_id, requested_by):
        calls.append((task_id, requested_by))
        return 'requested', {
            'task_id': task_id,
            'task_type': 'import_shipping',
            'status': 'running',
            'cancel_requested': True,
            'cancellable': False,
        }

    monkeypatch.setattr(
        shipping_repository,
        'request_task_cancel',
        request_cancel,
    )
    client = app.test_client()

    _set_user(client, username='viewer', permissions=['shipping:view'])
    denied = client.post(
        '/api/shipping/tasks/task-1/cancel',
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert denied.status_code == 403
    assert calls == []

    _set_user(
        client,
        username='editor',
        permissions=['shipping:view', 'shipping:edit'],
    )
    allowed = client.post(
        '/api/shipping/tasks/task-1/cancel',
        headers={'X-CSRF-Token': 'csrf'},
    )
    legacy = client.post(
        '/api/shipping/import/cancel/task-2',
        headers={'X-CSRF-Token': 'csrf'},
    )

    assert allowed.status_code == 200
    assert allowed.get_json()['message'] == '已发送取消请求'
    assert legacy.status_code == 200
    assert calls[0][0] == 'task-1'
    assert calls[1][0] == 'task-2'
    assert calls[0][1] == calls[1][1]
    assert calls[0][1] is not None
