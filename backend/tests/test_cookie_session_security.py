from flask import Flask, g
import pytest

import app as app_module
from auth import (
    clear_auth_cookies,
    clear_auth_cookies_on_unauthorized,
    generate_token,
    make_blueprint_guard,
    require_auth,
    set_auth_cookies,
    validate_csrf_request,
)
from database.repository.account import UserRepository
from result import Result
from routes.account import account_bp, account_service


def _user(user_id=7, csrf=None):
    return {
        'id': user_id,
        'username': f'user-{user_id}',
        'roles': ['staff'],
        'permissions': ['product:view', 'product:edit'],
        'token_version': 3,
        'csrf': csrf,
    }


def _csrf_app():
    app = Flask(__name__)
    app.before_request(validate_csrf_request)

    @app.route('/protected', methods=['GET', 'POST', 'OPTIONS'])
    @require_auth
    def protected():
        return Result.ok(data={'id': g.current_user['id']}).to_response()

    return app


def _set_session(client, *, user_id=7, csrf='csrf-token'):
    client.set_cookie('tmt_session', generate_token(_user(user_id), csrf_token=csrf))
    client.set_cookie('tmt_csrf', csrf)


def test_cookie_session_and_bound_csrf_are_accepted(monkeypatch):
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 3))
    client = _csrf_app().test_client()
    _set_session(client)

    response = client.post('/protected', headers={'X-CSRF-Token': 'csrf-token'})

    assert response.status_code == 200
    assert response.get_json()['data']['id'] == 7


def test_csrf_rejects_missing_header_cookie_and_wrong_value(monkeypatch):
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 3))
    client = _csrf_app().test_client()
    _set_session(client)

    assert client.post('/protected').status_code == 403
    assert client.post('/protected', headers={'X-CSRF-Token': 'wrong'}).status_code == 403
    client.delete_cookie('tmt_csrf')
    assert client.post(
        '/protected', headers={'X-CSRF-Token': 'csrf-token'},
    ).status_code == 403


def test_csrf_from_another_session_cannot_be_mixed(monkeypatch):
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 3))
    client = _csrf_app().test_client()
    client.set_cookie('tmt_session', generate_token(_user(), csrf_token='session-a'))
    client.set_cookie('tmt_csrf', 'session-b')

    response = client.post('/protected', headers={'X-CSRF-Token': 'session-b'})

    assert response.status_code == 403


def test_safe_methods_and_options_do_not_require_csrf(monkeypatch):
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 3))
    client = _csrf_app().test_client()
    _set_session(client)

    assert client.get('/protected').status_code == 200
    assert client.options('/protected').status_code == 200


def test_account_status_is_queried_only_once_for_authenticated_write(monkeypatch):
    calls = []
    monkeypatch.setattr(
        UserRepository, 'get_auth_state',
        lambda user_id: calls.append(user_id) or (True, 3),
    )
    client = _csrf_app().test_client()
    _set_session(client)

    response = client.post('/protected', headers={'X-CSRF-Token': 'csrf-token'})

    assert response.status_code == 200
    assert calls == [7]


def test_login_sets_secure_cookie_pair_without_token_in_body(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(account_bp, url_prefix='/api/account')
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setattr(
        account_service, 'verify_password',
        lambda *_args, **_kwargs: Result.ok(data=_user()),
    )

    response = app.test_client().post(
        '/api/account/login', json={'username': 'tester', 'password': 'secret'},
    )

    assert response.status_code == 200
    assert 'token' not in response.get_json()['data']
    cookies = response.headers.getlist('Set-Cookie')
    session_cookie = next(value for value in cookies if value.startswith('tmt_session='))
    csrf_cookie = next(value for value in cookies if value.startswith('tmt_csrf='))
    for value in (session_cookie, csrf_cookie):
        assert 'Secure' in value
        assert 'SameSite=Strict' in value
        assert 'Path=/' in value
        assert 'Max-Age=604800' in value
    assert 'HttpOnly' in session_cookie
    assert 'HttpOnly' not in csrf_cookie


def test_failed_login_does_not_overwrite_existing_cookies(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(account_bp, url_prefix='/api/account')
    monkeypatch.setattr(
        account_service, 'verify_password',
        lambda *_args, **_kwargs: Result.fail('账号或密码错误'),
    )

    response = app.test_client().post(
        '/api/account/login', json={'username': 'tester', 'password': 'wrong'},
    )

    assert response.status_code == 400
    assert response.headers.getlist('Set-Cookie') == []


def test_public_login_is_csrf_exempt_even_when_session_cookie_exists(monkeypatch):
    app = Flask(__name__)
    app.before_request(validate_csrf_request)
    app.register_blueprint(account_bp, url_prefix='/api/account')
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 3))
    monkeypatch.setattr(
        account_service, 'verify_password',
        lambda *_args, **_kwargs: Result.ok(data=_user()),
    )
    client = app.test_client()
    _set_session(client)

    response = client.post(
        '/api/account/login', json={'username': 'tester', 'password': 'secret'},
    )

    assert response.status_code == 200


def test_logout_is_idempotent_and_clears_both_cookies(monkeypatch):
    app = Flask(__name__)
    app.before_request(validate_csrf_request)
    app.register_blueprint(account_bp, url_prefix='/api/account')
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: None)
    client = app.test_client()
    client.set_cookie('tmt_session', 'expired-or-invalid')

    response = client.post('/api/account/logout')

    assert response.status_code == 200
    cookies = response.headers.getlist('Set-Cookie')
    assert any(value.startswith('tmt_session=;') and 'Max-Age=0' in value for value in cookies)
    assert any(value.startswith('tmt_csrf=;') and 'Max-Age=0' in value for value in cookies)


def test_valid_logout_requires_matching_csrf(monkeypatch):
    app = Flask(__name__)
    app.before_request(validate_csrf_request)
    app.register_blueprint(account_bp, url_prefix='/api/account')
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 3))
    client = app.test_client()
    _set_session(client)

    assert client.post('/api/account/logout').status_code == 403
    assert client.post(
        '/api/account/logout', headers={'X-CSRF-Token': 'csrf-token'},
    ).status_code == 200


def test_401_response_clears_both_auth_cookies(monkeypatch):
    app = Flask(__name__)
    monkeypatch.setenv('APP_ENV', 'test')
    with app.app_context():
        response = app.make_response(({'error': 'unauthorized'}, 401))
        response = clear_auth_cookies_on_unauthorized(response)

    cookies = response.headers.getlist('Set-Cookie')
    assert len(cookies) == 2
    assert all('Max-Age=0' in value for value in cookies)


def test_self_password_change_clears_current_session(monkeypatch):
    app = Flask(__name__)
    app.before_request(validate_csrf_request)
    app.register_blueprint(account_bp, url_prefix='/api/account')
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 3))
    monkeypatch.setattr(
        account_service, 'change_password',
        lambda *_args: Result.ok(message='密码已修改'),
    )
    client = app.test_client()
    _set_session(client)

    response = client.put(
        '/api/account/users/7/password',
        json={'old_password': 'old', 'new_password': 'new'},
        headers={'X-CSRF-Token': 'csrf-token'},
    )

    assert response.status_code == 200
    assert len(response.headers.getlist('Set-Cookie')) == 2


def test_user_manager_password_change_for_other_user_keeps_manager_session(monkeypatch):
    app = Flask(__name__)
    app.before_request(validate_csrf_request)
    app.register_blueprint(account_bp, url_prefix='/api/account')
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 3))
    monkeypatch.setattr(
        account_service, 'change_password',
        lambda *_args: Result.ok(message='密码已修改'),
    )
    admin = _user(user_id=1)
    admin['roles'] = ['manager']
    admin['permissions'] = ['account:users:edit']
    client = app.test_client()
    client.set_cookie('tmt_session', generate_token(admin, csrf_token='admin-csrf'))
    client.set_cookie('tmt_csrf', 'admin-csrf')

    response = client.put(
        '/api/account/users/7/password',
        json={'old_password': 'ignored', 'new_password': 'new'},
        headers={'X-CSRF-Token': 'admin-csrf'},
    )

    assert response.status_code == 200
    assert response.headers.getlist('Set-Cookie') == []


def test_non_production_cookie_is_not_secure(monkeypatch):
    app = Flask(__name__)
    monkeypatch.setenv('APP_ENV', 'test')
    with app.app_context():
        response = set_auth_cookies(Result.ok(_user()).to_response(), _user())

    assert all('Secure' not in value for value in response.headers.getlist('Set-Cookie'))


def test_clear_auth_cookies_uses_root_path(monkeypatch):
    app = Flask(__name__)
    monkeypatch.setenv('APP_ENV', 'test')
    with app.app_context():
        response = clear_auth_cookies(Result.ok().to_response())

    cookies = response.headers.getlist('Set-Cookie')
    assert len(cookies) == 2
    assert all('Path=/' in value and 'Max-Age=0' in value for value in cookies)


def test_cors_credentials_require_explicit_origins(monkeypatch):
    monkeypatch.setenv('CORS_ORIGINS', '*')
    with pytest.raises(RuntimeError, match='禁止使用通配符'):
        app_module._get_cors_origins()

    monkeypatch.setenv('CORS_ORIGINS', 'https://tmt-library.cn, http://localhost:5174')
    assert app_module._get_cors_origins() == [
        'https://tmt-library.cn', 'http://localhost:5174',
    ]


def test_auth_is_imported_only_after_dotenv_load():
    source = app_module.Path(app_module.__file__).read_text(encoding='utf-8')

    assert source.index('load_dotenv(') < source.index('from auth import')


def test_blueprint_guard_accepts_cookie_and_rejects_bearer(monkeypatch):
    app = Flask(__name__)
    app.before_request(make_blueprint_guard('product:view', 'product:edit'))

    @app.get('/items')
    def items():
        return Result.ok().to_response()

    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 3))
    token = generate_token(_user(), csrf_token='csrf-token')
    client = app.test_client()

    assert client.get(
        '/items', headers={'Authorization': f'Bearer {token}'},
    ).status_code == 401
    client.set_cookie('tmt_session', token)
    assert client.get('/items').status_code == 200


def test_no_runtime_guard_reads_authorization_header():
    backend_dir = app_module.Path(app_module.__file__).parent
    sources = [
        backend_dir / 'auth.py',
        backend_dir / 'routes' / 'account' / '__init__.py',
        backend_dir / 'routes' / 'version' / '__init__.py',
    ]

    for source_path in sources:
        source = source_path.read_text(encoding='utf-8')
        assert "headers.get('Authorization'" not in source
        assert 'removeprefix(\'Bearer\')' not in source
