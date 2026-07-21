from types import SimpleNamespace

from flask import Flask, g

from auth import generate_token, require_auth
from database.repository.account import RoleRepository, UserRepository
from result import Result
from services.account import AccountService


def _user_payload(token_version=0):
    return {
        'id': 7,
        'username': 'tester',
        'roles': ['staff'],
        'permissions': ['product:view'],
        'token_version': token_version,
    }


def _protected_app():
    app = Flask(__name__)

    @app.get('/protected')
    @require_auth
    def protected():
        return Result.ok(data=g.current_user, message='ok').to_response()

    return app


def _request(token):
    client = _protected_app().test_client()
    client.set_cookie('tmt_session', token)
    return client.get('/protected')


def test_bearer_token_is_no_longer_accepted(monkeypatch):
    token = generate_token(_user_payload(token_version=3))
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 3))

    response = _protected_app().test_client().get(
        '/protected', headers={'Authorization': f'Bearer {token}'},
    )

    assert response.status_code == 401


def test_current_active_token_is_accepted(monkeypatch):
    token = generate_token(_user_payload(token_version=3))
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 3))

    response = _request(token)

    assert response.status_code == 200
    assert response.get_json()['data']['permissions'] == ['product:view']


def test_disabled_account_rejects_existing_token_with_standard_401(monkeypatch):
    token = generate_token(_user_payload(token_version=3))
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (False, 4))

    response = _request(token)

    assert response.status_code == 401
    assert response.get_json()['success'] is False


def test_password_change_rejects_previous_token_with_standard_401(monkeypatch):
    token = generate_token(_user_payload(token_version=3))
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 4))

    response = _request(token)

    assert response.status_code == 401


def test_deleted_account_rejects_existing_token(monkeypatch):
    token = generate_token(_user_payload(token_version=3))
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: None)

    response = _request(token)

    assert response.status_code == 401


def test_guest_token_uses_current_guest_permissions(monkeypatch):
    token = generate_token({
        'id': None,
        'username': 'guest',
        'roles': ['guest'],
        'permissions': ['stale:permission'],
    })
    guest_role = SimpleNamespace(
        permissions=[SimpleNamespace(code='product:view')],
    )
    monkeypatch.setattr(RoleRepository, 'get_by_name', lambda _name: guest_role)

    response = _request(token)

    assert response.status_code == 200
    assert response.get_json()['data']['permissions'] == ['product:view']


def test_user_update_can_increment_token_version_without_database(monkeypatch):
    user = SimpleNamespace(token_version=5, is_active=True)
    commits = []
    monkeypatch.setattr(
        'database.repository.account.db.session.commit',
        lambda: commits.append(True),
    )

    updated = UserRepository.update(
        user,
        invalidate_tokens=True,
        is_active=False,
    )

    assert updated.is_active is False
    assert updated.token_version == 6
    assert commits == [True]


def test_assigning_and_removing_role_each_invalidates_tokens(monkeypatch):
    role = object()
    user = SimpleNamespace(token_version=0, roles=[])
    commits = []
    monkeypatch.setattr(
        'database.repository.account.db.session.commit',
        lambda: commits.append(True),
    )

    UserRepository.assign_role(user, role)
    UserRepository.remove_role(user, role)

    assert user.token_version == 2
    assert commits == [True, True]


def test_change_password_requests_token_invalidation(monkeypatch):
    service = AccountService()
    user = SimpleNamespace(
        id=7,
        password='$2b$12$D0FTZwH8Q7QJBtquvH7aHeP7DB0lPaYrEd2a4Lx3gB53q9Kz3qM3u',
    )
    updates = []
    monkeypatch.setattr(UserRepository, 'get_by_id', lambda _id: user)
    monkeypatch.setattr('services.account.bcrypt.checkpw', lambda *_args: True)
    monkeypatch.setattr('services.account.bcrypt.hashpw', lambda *_args: b'new-hash')
    monkeypatch.setattr(UserRepository, 'update', lambda _user, **kwargs: updates.append(kwargs))

    result = service.change_password(7, 'old-password', 'new-password')

    assert result.success is True
    assert updates == [{'invalidate_tokens': True, 'password': 'new-hash'}]


def test_disabling_account_requests_token_invalidation(monkeypatch):
    service = AccountService()
    user = SimpleNamespace(id=7, username='tester')
    updates = []
    monkeypatch.setattr(UserRepository, 'get_by_id', lambda _id: user)
    monkeypatch.setattr(UserRepository, 'update', lambda _user, **kwargs: updates.append(kwargs))

    result = service.set_user_status(7, False)

    assert result.success is True
    assert updates == [{'invalidate_tokens': True, 'is_active': False}]
