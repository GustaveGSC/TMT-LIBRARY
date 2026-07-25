from flask import Flask

import routes.shipping as shipping_routes


def test_resolve_all_fails_fast_before_creating_task(monkeypatch):
    app = Flask(__name__)
    monkeypatch.delenv('ALLOW_FULL_RESOLVE', raising=False)
    task_creation_called = False

    def unexpected_task_creation(*_args, **_kwargs):
        nonlocal task_creation_called
        task_creation_called = True
        raise AssertionError('disabled resolve-all must not create a task')

    monkeypatch.setattr(
        shipping_routes, '_create_mutation_task', unexpected_task_creation,
    )

    with app.test_request_context('/api/shipping/resolve-all', method='POST'):
        response, status = shipping_routes.resolve_all()

    assert status == 503
    assert response.get_json() == {
        'success': False,
        'message': '全量重建正在维护优化，当前暂不可用',
    }
    assert task_creation_called is False


def test_resolve_all_gate_accepts_explicit_true_values(monkeypatch):
    for value in ('1', 'true', 'TRUE', ' yes ', 'on'):
        monkeypatch.setenv('ALLOW_FULL_RESOLVE', value)
        assert shipping_routes._is_full_resolve_enabled() is True

    for value in ('', '0', 'false', 'off', 'unexpected'):
        monkeypatch.setenv('ALLOW_FULL_RESOLVE', value)
        assert shipping_routes._is_full_resolve_enabled() is False
