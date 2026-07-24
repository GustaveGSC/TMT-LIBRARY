from flask import Flask

from routes import aftersale as aftersale_routes


def _call(app, path, view, *, json=None):
    with app.test_request_context(path, json=json):
        response, status = view()
        return status, response.get_json()


def test_pending_rejects_invalid_and_unbounded_pagination():
    app = Flask(__name__)

    status, payload = _call(
        app, '/pending?page=not-a-number', aftersale_routes.get_pending,
    )
    assert status == 400
    assert payload['message'] == 'page 和 page_size 必须是整数'

    status, payload = _call(
        app, '/pending?page=0&page_size=201', aftersale_routes.get_pending,
    )
    assert status == 400
    assert payload['message'] == 'page 必须大于等于 1'

    status, payload = _call(
        app, '/pending?page=1&page_size=201', aftersale_routes.get_pending,
    )
    assert status == 400
    assert payload['message'] == 'page_size 必须在 1 到 200 之间'


def test_cases_rejects_invalid_or_excessive_id_lists():
    app = Flask(__name__)

    status, payload = _call(
        app, '/cases?model_ids=1,-2', aftersale_routes.get_cases,
    )
    assert status == 400
    assert payload['message'] == 'ID 必须是正整数'

    ids = ','.join(str(value) for value in range(1, 202))
    status, payload = _call(
        app, f'/cases/reasons?ids={ids}', aftersale_routes.get_cases_reasons,
    )
    assert status == 400
    assert payload['message'] == 'ID 数量不能超过 200'


def test_alias_affinity_rejects_unbounded_or_invalid_ids():
    app = Flask(__name__)

    status, payload = _call(
        app,
        '/alias-affinity',
        aftersale_routes.get_alias_affinity,
        json={'reason_id': 1, 'alias_ids': list(range(1, 202))},
    )
    assert status == 400
    assert payload['message'] == 'alias_ids 必须是数组且不能超过 200 个'

    status, payload = _call(
        app,
        '/alias-affinity',
        aftersale_routes.get_alias_affinity,
        json={'reason_id': 1, 'alias_ids': [0]},
    )
    assert status == 400
    assert payload['message'] == 'reason_id 和 alias_ids 必须是正整数'
