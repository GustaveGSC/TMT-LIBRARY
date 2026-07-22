import json

from flask import Flask

from auth import generate_token
from database.repository.account import UserRepository
from routes.config import config_bp
from services.config import config_service


def test_motto_service_falls_back_for_missing_or_invalid_json(monkeypatch):
    monkeypatch.setattr(
        'services.config.site_config_repository.get_value',
        lambda _key: '{invalid',
    )

    result = config_service.get_login_mottos()

    assert result
    assert result == config_service.get_login_mottos()
    assert result is not config_service.get_login_mottos()


def test_motto_service_normalizes_and_persists_json(monkeypatch):
    saved = {}
    monkeypatch.setattr(
        'services.config.site_config_repository.set_value',
        lambda key, value: saved.update(key=key, value=value),
    )

    result = config_service.update_login_mottos({'mottos': [' 甲 ', '', 2]})

    assert result == ['甲', '2']
    assert saved['key'] == 'login_mottos'
    assert json.loads(saved['value']) == result


def test_motto_routes_preserve_public_read_and_admin_write_contract(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(config_bp, url_prefix='/api/config')
    monkeypatch.setattr(UserRepository, 'get_auth_state', lambda _id: (True, 0))
    monkeypatch.setattr(config_service, 'get_login_mottos', lambda: ['测试语句'])
    monkeypatch.setattr(
        config_service, 'update_login_mottos',
        lambda payload: payload['mottos'],
    )
    client = app.test_client()

    response = client.get('/api/config/login-mottos')
    assert response.status_code == 200
    assert response.get_json()['data'] == ['测试语句']

    viewer = {
        'id': 1, 'username': 'viewer', 'roles': [], 'permissions': [],
        'token_version': 0,
    }
    client.set_cookie('tmt_session', generate_token(viewer, csrf_token='csrf'))
    response = client.put(
        '/api/config/login-mottos', json={'mottos': ['新语句']},
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert response.status_code == 403

    admin = {**viewer, 'username': 'admin', 'roles': ['admin']}
    client.set_cookie('tmt_session', generate_token(admin, csrf_token='csrf'))
    response = client.put(
        '/api/config/login-mottos', json={'mottos': ['新语句']},
        headers={'X-CSRF-Token': 'csrf'},
    )
    assert response.status_code == 200
    assert response.get_json()['data'] == ['新语句']
