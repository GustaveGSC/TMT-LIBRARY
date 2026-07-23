from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy.exc import IntegrityError

import routes.account as account_routes
from database.repository.account import LoginLogRepository, UserRepository
from rate_limit import limiter
from result import Result
from services.account import MAX_PASSWORD_BYTES, account_service


def _user(username="tester"):
    return SimpleNamespace(
        id=7,
        username=username,
        password="stored-hash",
        display_name="Tester",
        is_active=True,
        to_dict=lambda: {
            "id": 7,
            "username": username,
            "display_name": "Tester",
            "is_active": True,
            "roles": [],
            "permissions": [],
        },
    )


@pytest.mark.parametrize("method_name", ["create_user", "reset_password"])
def test_password_rule_rejects_short_password_at_service_boundary(monkeypatch, method_name):
    monkeypatch.setattr(UserRepository, "get_by_id", lambda _user_id: _user())
    monkeypatch.setattr(UserRepository, "get_by_username", lambda _username: None)

    if method_name == "create_user":
        result = account_service.create_user("tester", "12345")
    else:
        result = account_service.reset_password(7, "12345")

    assert not result.success
    assert "至少 6 位" in result.message


def test_update_user_rejects_short_password(monkeypatch):
    monkeypatch.setattr(UserRepository, "get_by_id", lambda _user_id: _user())

    result = account_service.update_user(7, password="12345")

    assert not result.success
    assert "至少 6 位" in result.message


def test_change_password_rejects_password_over_bcrypt_byte_limit(monkeypatch):
    monkeypatch.setattr(UserRepository, "get_by_id", lambda _user_id: _user())
    monkeypatch.setattr("services.account.bcrypt.checkpw", lambda *_args: True)

    result = account_service.change_password(7, "old-password", "密" * 25)

    assert not result.success
    assert str(MAX_PASSWORD_BYTES) in result.message


def test_create_user_converts_unique_constraint_race_to_business_error(monkeypatch):
    monkeypatch.setattr(UserRepository, "get_by_username", lambda _username: None)
    monkeypatch.setattr("services.account.bcrypt.hashpw", lambda *_args: b"hash")
    monkeypatch.setattr("services.account.bcrypt.gensalt", lambda: b"salt")
    monkeypatch.setattr(
        UserRepository,
        "create",
        lambda *_args: (_ for _ in ()).throw(
            IntegrityError("insert", {}, Exception("duplicate"))
        ),
    )
    rolled_back = []
    monkeypatch.setattr("services.account.db.session.rollback", lambda: rolled_back.append(True))

    result = account_service.create_user("tester", "123456")

    assert not result.success
    assert "已存在" in result.message
    assert rolled_back == [True]


def test_missing_and_existing_user_both_execute_bcrypt(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "services.account.bcrypt.checkpw",
        lambda password, password_hash: calls.append((password, password_hash)) or False,
    )
    monkeypatch.setattr(LoginLogRepository, "create", lambda **_kwargs: None)

    monkeypatch.setattr(UserRepository, "get_by_username", lambda _username: None)
    missing = account_service.verify_password("missing", "secret")
    monkeypatch.setattr(UserRepository, "get_by_username", lambda _username: _user())
    existing = account_service.verify_password("tester", "secret")

    assert not missing.success
    assert not existing.success
    assert len(calls) == 2
    assert calls[0][1] != calls[1][1]


@pytest.fixture
def limited_account_app(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, RATELIMIT_ENABLED=True)
    limiter.init_app(app)
    app.register_blueprint(account_routes.account_bp, url_prefix="/api/account")
    limiter.reset()
    monkeypatch.setattr(account_routes, "_machine_name", lambda: "test-machine")
    monkeypatch.setattr(
        account_routes,
        "set_auth_cookies",
        lambda response, _user_data: response,
    )
    yield app
    limiter.reset()


def _login(client, username="tester", ip_header="198.51.100.10", remote_addr=None):
    headers = {"X-Real-IP": ip_header} if ip_header is not None else {}
    environ = {"REMOTE_ADDR": remote_addr} if remote_addr else {}
    return client.post(
        "/api/account/login",
        json={"username": username, "password": "wrong-password"},
        headers=headers,
        environ_overrides=environ,
    )


def test_login_account_limit_returns_standard_429(limited_account_app, monkeypatch):
    monkeypatch.setattr(
        account_routes.account_service,
        "verify_password",
        lambda *_args, **_kwargs: Result.fail("用户名或密码错误"),
    )
    client = limited_account_app.test_client()

    for _ in range(5):
        assert _login(client).status_code == 400
    response = _login(client)

    assert response.status_code == 429
    assert response.get_json() == {
        "success": False,
        "message": "尝试次数过多，请稍后重试",
    }


def test_successful_login_clears_only_account_failure_counter(
    limited_account_app, monkeypatch
):
    results = [Result.fail("用户名或密码错误")] * 4 + [
        Result.ok(_user().to_dict())
    ] + [Result.fail("用户名或密码错误")] * 6
    monkeypatch.setattr(
        account_routes.account_service,
        "verify_password",
        lambda *_args, **_kwargs: results.pop(0),
    )
    client = limited_account_app.test_client()

    for _ in range(4):
        assert _login(client).status_code == 400
    assert _login(client).status_code == 200
    for _ in range(5):
        assert _login(client).status_code == 400
    assert _login(client).status_code == 429


def test_login_ip_limit_covers_rotating_usernames(limited_account_app, monkeypatch):
    monkeypatch.setattr(
        account_routes.account_service,
        "verify_password",
        lambda *_args, **_kwargs: Result.fail("用户名或密码错误"),
    )
    client = limited_account_app.test_client()

    for index in range(20):
        assert _login(client, username=f"user-{index}").status_code == 400
    assert _login(client, username="user-20").status_code == 429


def test_client_ip_falls_back_to_remote_addr(limited_account_app, monkeypatch):
    monkeypatch.setattr(
        account_routes.account_service,
        "verify_password",
        lambda *_args, **_kwargs: Result.fail("用户名或密码错误"),
    )
    client = limited_account_app.test_client()

    for _ in range(5):
        assert _login(
            client, username="first-user", ip_header=None, remote_addr="198.51.100.20"
        ).status_code == 400
    assert _login(
        client, username="second-user", ip_header=None, remote_addr="198.51.100.21"
    ).status_code == 400


def test_registration_ip_limit_and_disabled_exemption(
    limited_account_app, monkeypatch
):
    client = limited_account_app.test_client()
    monkeypatch.setenv("ALLOW_REGISTER", "false")
    for _ in range(6):
        assert client.post(
            "/api/account/register",
            json={"username": "tester", "password": "123456"},
            headers={"X-Real-IP": "198.51.100.30"},
        ).status_code == 403

    monkeypatch.setenv("ALLOW_REGISTER", "true")
    monkeypatch.setattr(
        account_routes.account_service,
        "create_user",
        lambda *_args, **_kwargs: Result.ok({"id": 7}),
    )
    for index in range(5):
        assert client.post(
            "/api/account/register",
            json={"username": f"tester-{index}", "password": "123456"},
            headers={"X-Real-IP": "198.51.100.30"},
        ).status_code == 200
    response = client.post(
        "/api/account/register",
        json={"username": "tester-5", "password": "123456"},
        headers={"X-Real-IP": "198.51.100.30"},
    )
    assert response.status_code == 429
