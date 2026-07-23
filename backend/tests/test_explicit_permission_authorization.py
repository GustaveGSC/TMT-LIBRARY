from types import SimpleNamespace

from flask import Flask, g
import pytest

from auth import generate_token, has_permission, is_rd_admin
from database.repository.account import RoleRepository, UserRepository
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


@pytest.mark.parametrize('method', ['post', 'delete'])
def test_manager_cannot_assign_or_remove_admin_role(
    account_client, monkeypatch, method
):
    monkeypatch.setattr(
        UserRepository, 'get_by_id',
        lambda _user_id: SimpleNamespace(id=9, roles=[], token_version=0),
    )
    monkeypatch.setattr(
        RoleRepository, 'get_by_id',
        lambda _role_id: SimpleNamespace(id=1, name='admin'),
    )
    mutated = []
    monkeypatch.setattr(
        UserRepository, 'assign_role',
        lambda *_args: mutated.append('assigned'),
    )
    monkeypatch.setattr(
        UserRepository, 'remove_role',
        lambda *_args: mutated.append('removed'),
    )
    _set_user(
        account_client,
        username='manager',
        roles=['manager'],
        permissions=['account:users:edit'],
    )

    response = getattr(account_client, method)('/api/account/users/9/roles/1')

    assert response.status_code == 403
    assert response.get_json()['data']['error_code'] == 'admin_role_requires_admin'
    assert mutated == []


def test_manager_can_assign_non_admin_role(account_client, monkeypatch):
    monkeypatch.setattr(
        UserRepository, 'get_by_id',
        lambda _user_id: SimpleNamespace(id=9, roles=[], token_version=0),
    )
    monkeypatch.setattr(
        RoleRepository, 'get_by_id',
        lambda _role_id: SimpleNamespace(id=2, name='developer'),
    )
    assigned = []
    monkeypatch.setattr(
        UserRepository, 'assign_role',
        lambda user, role: assigned.append((user.id, role.name)),
    )
    _set_user(
        account_client,
        username='manager',
        roles=['manager'],
        permissions=['account:users:edit'],
    )

    response = account_client.post('/api/account/users/9/roles/2')

    assert response.status_code == 200
    assert assigned == [(9, 'developer')]


def test_service_denies_admin_role_mutation_without_operator_context(monkeypatch):
    monkeypatch.setattr(
        UserRepository, 'get_by_id',
        lambda _user_id: SimpleNamespace(id=9, roles=[], token_version=0),
    )
    monkeypatch.setattr(
        RoleRepository, 'get_by_id',
        lambda _role_id: SimpleNamespace(id=1, name='admin'),
    )
    monkeypatch.setattr(
        UserRepository, 'assign_role',
        lambda *_args: pytest.fail('admin role mutation must not reach repository'),
    )

    result = account_service.assign_role(9, 1)

    assert not result.success
    assert result.data['error_code'] == 'admin_role_requires_admin'


def test_builtin_admin_role_cannot_be_deleted(account_client, monkeypatch):
    monkeypatch.setattr(
        RoleRepository, 'get_by_id',
        lambda _role_id: SimpleNamespace(id=1, name='admin'),
    )
    monkeypatch.setattr(
        RoleRepository, 'delete',
        lambda *_args: pytest.fail('built-in admin role must not be deleted'),
    )
    _set_user(
        account_client,
        username='admin',
        roles=['admin'],
        permissions=['account:roles:edit'],
    )

    response = account_client.delete('/api/account/roles/1')

    assert response.status_code == 403
    assert response.get_json()['data']['error_code'] == 'admin_role_requires_admin'


def test_user_update_cannot_bypass_role_guard_with_mass_assignment(
    account_client, monkeypatch
):
    monkeypatch.setattr(
        UserRepository, 'get_by_id',
        lambda _user_id: SimpleNamespace(id=9, username='admin'),
    )
    monkeypatch.setattr(
        UserRepository, 'update',
        lambda *_args, **_kwargs: pytest.fail('mass assignment must not reach repository'),
    )
    _set_user(
        account_client,
        username='manager',
        roles=['manager'],
        permissions=['account:users:edit'],
    )

    response = account_client.put(
        '/api/account/users/9',
        json={'roles': [], 'token_version': 999, 'is_active': False},
    )

    assert response.status_code == 400
    assert '不允许' in response.get_json()['message']


def test_manager_cannot_reset_protected_account_password(
    account_client, monkeypatch
):
    monkeypatch.setattr(
        UserRepository, 'get_by_id',
        lambda _user_id: SimpleNamespace(id=9, username='admin'),
    )
    _set_user(
        account_client,
        username='manager',
        roles=['manager'],
        permissions=['account:users:edit'],
    )

    response = account_client.post(
        '/api/account/users/9/reset-password',
        json={'new_password': 'new-password'},
    )

    assert response.status_code == 403
    assert response.get_json()['data']['error_code'] == 'protected_account_requires_admin'


def test_admin_can_reset_protected_account_password(account_client, monkeypatch):
    protected_user = SimpleNamespace(id=9, username='author')
    monkeypatch.setattr(UserRepository, 'get_by_id', lambda _user_id: protected_user)
    monkeypatch.setattr('services.account.bcrypt.hashpw', lambda *_args: b'new-hash')
    monkeypatch.setattr('services.account.bcrypt.gensalt', lambda: b'salt')
    updates = []
    monkeypatch.setattr(
        UserRepository, 'update',
        lambda user, **kwargs: updates.append((user.id, kwargs)),
    )
    _set_user(
        account_client,
        username='admin',
        roles=['admin'],
        permissions=['account:users:edit'],
    )

    response = account_client.post(
        '/api/account/users/9/reset-password',
        json={'new_password': 'new-password'},
    )

    assert response.status_code == 200
    assert updates[0][0] == 9
    assert updates[0][1]['invalidate_tokens'] is True


@pytest.mark.parametrize(
    ('username', 'roles'),
    [
        ('admin', ['admin']),
        ('author', ['admin', 'developer']),
    ],
)
def test_existing_admin_holders_cannot_assign_admin_role(
    account_client, monkeypatch, username, roles
):
    monkeypatch.setattr(
        UserRepository, 'get_by_id',
        lambda _user_id: SimpleNamespace(id=9, roles=[], token_version=0),
    )
    monkeypatch.setattr(
        RoleRepository, 'get_by_id',
        lambda _role_id: SimpleNamespace(id=1, name='admin'),
    )
    mutated = []
    monkeypatch.setattr(
        UserRepository, 'assign_role',
        lambda *_args: mutated.append('assigned'),
    )
    _set_user(
        account_client,
        username=username,
        roles=roles,
        permissions=['account:users:edit'],
    )

    response = account_client.post('/api/account/users/9/roles/1')

    assert response.status_code == 403
    assert response.get_json()['message'] == 'admin 角色已停止分配，仅保留现有持有者'
    assert mutated == []


def test_admin_can_still_remove_admin_role(account_client, monkeypatch):
    monkeypatch.setattr(
        UserRepository, 'get_by_id',
        lambda _user_id: SimpleNamespace(id=9, roles=[], token_version=0),
    )
    monkeypatch.setattr(
        RoleRepository, 'get_by_id',
        lambda _role_id: SimpleNamespace(id=1, name='admin'),
    )
    removed = []
    monkeypatch.setattr(
        UserRepository, 'remove_role',
        lambda *_args: removed.append(True),
    )
    _set_user(
        account_client,
        username='admin',
        roles=['admin'],
        permissions=['account:users:edit'],
    )

    response = account_client.delete('/api/account/users/9/roles/1')

    assert response.status_code == 200
    assert removed == [True]


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
