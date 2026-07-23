from flask import Flask, g
import pytest

from auth import generate_token, has_permission, is_rd_admin
from database.repository.account import UserRepository
from result import Result
from routes.account import account_bp
from routes.product.resource import resource_bp
from services.account import account_service
from services.product.resource import resource_service


def _set_user(client, *, username='tester', roles=None, permissions=None):
    payload = {
        'id': 7,
        'username': username,
        'roles': roles or [],
        'permissions': permissions or [],
        'token_version': 0,
    }
    client.set_cookie('tmt_session', generate_token(payload, csrf_token='csrf'))
    client.set_cookie('tmt_csrf', 'csrf')


def test_role_name_and_username_do_not_bypass_explicit_permissions():
    assert not has_permission(
        {'username': 'admin', 'roles': ['admin'], 'permissions': []},
        'account:users:view',
    )
    assert not has_permission(
        {'username': 'author', 'roles': [], 'permissions': []},
        'developer:analytics:view',
    )
    assert has_permission(
        {'roles': [], 'permissions': ['account:users:view']},
        'account:users:view',
    )


def test_rd_admin_requires_explicit_permission():
    app = Flask(__name__)
    with app.test_request_context():
        g.current_user = {'roles': ['admin'], 'permissions': []}
        assert not is_rd_admin()
        g.current_user = {'roles': [], 'permissions': ['rd:admin']}
        assert is_rd_admin()


@pytest.fixture
def account_client(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(account_bp, url_prefix='/api/account')
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 0))
    monkeypatch.setattr(
        account_service, 'get_users',
        lambda **_kwargs: Result.ok({'items': [], 'total': 0}),
    )
    monkeypatch.setattr(
        account_service, 'create_user',
        lambda *_args, **_kwargs: Result.ok({'id': 10}),
    )
    monkeypatch.setattr(account_service, 'get_roles', lambda: Result.ok([]))
    monkeypatch.setattr(
        account_service, 'create_role',
        lambda *_args, **_kwargs: Result.ok({'id': 11}),
    )
    monkeypatch.setattr(account_service, 'get_login_logs', lambda **_kwargs: Result.ok([]))
    return app.test_client()


@pytest.mark.parametrize(
    ('method', 'path', 'permission', 'json_body'),
    [
        ('get', '/api/account/users', 'account:users:view', None),
        ('post', '/api/account/users', 'account:users:edit', {
            'username': 'new-user', 'password': '123456',
        }),
        ('get', '/api/account/roles', 'account:roles:view', None),
        ('post', '/api/account/roles', 'account:roles:edit', {'name': 'new-role'}),
        ('get', '/api/account/login-logs', 'developer:analytics:view', None),
    ],
)
def test_account_endpoint_matrix_requires_exact_permission(
    account_client, method, path, permission, json_body
):
    _set_user(account_client, permissions=[])
    denied = getattr(account_client, method)(path, json=json_body)
    assert denied.status_code == 403

    _set_user(account_client, permissions=[permission])
    allowed = getattr(account_client, method)(path, json=json_body)
    assert allowed.status_code == 200


def test_legacy_admin_role_without_permissions_is_denied(account_client):
    _set_user(account_client, username='admin', roles=['admin'], permissions=[])

    assert account_client.get('/api/account/users').status_code == 403


def test_author_username_without_developer_permission_is_denied(account_client):
    _set_user(account_client, username='author', permissions=[])

    assert account_client.get('/api/account/login-logs').status_code == 403


def test_product_type_management_uses_product_edit_not_admin_role(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(resource_bp, url_prefix='/api/resources')
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 0))
    monkeypatch.setattr(
        resource_service, 'create_type',
        lambda *_args, **_kwargs: Result.ok({'id': 3}),
    )
    client = app.test_client()

    _set_user(client, username='admin', roles=['admin'], permissions=['product:view'])
    assert client.post('/api/resources/types', json={'name': '手册'}).status_code == 403

    _set_user(client, roles=['product-editor'], permissions=['product:view', 'product:edit'])
    assert client.post('/api/resources/types', json={'name': '手册'}).status_code == 200
