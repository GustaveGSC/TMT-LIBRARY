import threading
import uuid

import pytest
from flask import Flask, g

from database.base import db
from database.models.shipping import ShippingTask
from database.repository.shipping import ShippingRepository
from routes import shipping as shipping_routes


LEASE_KEY = 'shipping_data_mutation'


def _app(database_path):
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{database_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        ShippingTask.__table__.create(db.engine)
    return app


def _create(repository, task_id, task_type='import_shipping'):
    repository.create_task(
        task_id,
        task_type,
        lease_key=LEASE_KEY,
    )
    repository.update_task(task_id, status='running')


def test_cancel_request_is_persisted_idempotent_and_keeps_lease(tmp_path):
    app = _app(tmp_path / 'cancel.db')
    task_id = str(uuid.uuid4())

    with app.app_context():
        _create(ShippingRepository, task_id)

        outcome, snapshot = ShippingRepository.request_task_cancel(task_id, 17)
        repeated, repeated_snapshot = ShippingRepository.request_task_cancel(
            task_id, 99,
        )
        task = db.session.get(ShippingTask, task_id)

        assert outcome == 'requested'
        assert snapshot['cancel_requested'] is True
        assert snapshot['cancellable'] is False
        assert repeated == 'already_requested'
        assert repeated_snapshot['cancel_requested'] is True
        assert task.cancel_requested_by == 17
        assert task.cancel_requested_at is not None
        assert task.lease_key == LEASE_KEY
        assert ShippingRepository.is_cancel_requested(task_id) is True


def test_cancel_rejects_unsupported_committing_finished_and_missing(tmp_path):
    app = _app(tmp_path / 'cancel-states.db')

    with app.app_context():
        unsupported_id = str(uuid.uuid4())
        _create(ShippingRepository, unsupported_id, 'legacy_unknown')
        assert ShippingRepository.request_task_cancel(
            unsupported_id, 1,
        )[0] == 'unsupported'
        ShippingRepository.update_task(unsupported_id, status='done')

        resolve_id = str(uuid.uuid4())
        _create(ShippingRepository, resolve_id, 'resolve_all')
        assert ShippingRepository.request_task_cancel(
            resolve_id, 1,
        )[0] == 'requested'
        ShippingRepository.update_task(resolve_id, status='cancelled')

        committing_id = str(uuid.uuid4())
        _create(ShippingRepository, committing_id)
        assert ShippingRepository.try_begin_commit(committing_id) is True
        assert ShippingRepository.request_task_cancel(
            committing_id, 1,
        )[0] == 'committing'
        ShippingRepository.update_task(committing_id, status='done')

        finished_id = str(uuid.uuid4())
        _create(ShippingRepository, finished_id)
        ShippingRepository.update_task(finished_id, status='done')
        assert ShippingRepository.request_task_cancel(
            finished_id, 1,
        )[0] == 'finished'
        assert ShippingRepository.request_task_cancel(
            str(uuid.uuid4()), 1,
        )[0] == 'not_found'


def test_cancel_and_committing_compare_and_set_have_single_winner(tmp_path):
    app = _app(tmp_path / 'cancel-race.db')
    task_id = str(uuid.uuid4())
    with app.app_context():
        _create(ShippingRepository, task_id)

    barrier = threading.Barrier(2)
    outcomes = {}
    lock = threading.Lock()

    def request_cancel():
        with app.app_context():
            barrier.wait()
            outcome = ShippingRepository.request_task_cancel(task_id, 23)[0]
            with lock:
                outcomes['cancel'] = outcome

    def begin_commit():
        with app.app_context():
            barrier.wait()
            outcome = ShippingRepository.try_begin_commit(task_id)
            with lock:
                outcomes['commit'] = outcome

    threads = [
        threading.Thread(target=request_cancel),
        threading.Thread(target=begin_commit),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert outcomes in (
        {'cancel': 'requested', 'commit': False},
        {'cancel': 'committing', 'commit': True},
    )
    with app.app_context():
        task = db.session.get(ShippingTask, task_id)
        assert task.lease_key == LEASE_KEY
        assert (task.status == 'committing') != (
            task.cancel_requested_at is not None
        )


def test_reload_interrupts_committing_task_and_releases_lease(tmp_path):
    app = _app(tmp_path / 'cancel-reload.db')
    task_id = str(uuid.uuid4())

    with app.app_context():
        _create(ShippingRepository, task_id)
        assert ShippingRepository.try_begin_commit(task_id) is True
        assert ShippingRepository.interrupt_running_tasks() == 1
        task = db.session.get(ShippingTask, task_id)
        assert task.status == 'interrupted'
        assert task.lease_key is None


@pytest.mark.parametrize(
    ('outcome', 'expected_status', 'expected_message'),
    (
        ('not_found', 404, '任务不存在'),
        ('unsupported', 400, '该任务暂不支持取消'),
        ('committing', 409, '任务正在提交最终结果，已无法取消'),
        ('finished', 400, '任务已经结束，无法取消'),
        ('already_requested', 200, '已发送取消请求'),
    ),
)
def test_cancel_route_maps_repository_outcomes(
    monkeypatch, outcome, expected_status, expected_message,
):
    app = Flask(__name__)
    snapshot = None if outcome == 'not_found' else {
        'task_id': 'task-1',
        'task_type': 'import_shipping',
        'status': 'running',
        'cancel_requested': outcome == 'already_requested',
        'cancellable': False,
    }
    monkeypatch.setattr(
        shipping_routes.shipping_repository,
        'request_task_cancel',
        lambda *_args, **_kwargs: (outcome, snapshot),
    )

    with app.test_request_context('/api/shipping/tasks/task-1/cancel', method='POST'):
        g.current_user = {'id': 7}
        response, status = shipping_routes._cancel_task_response('task-1')

    assert status == expected_status
    assert response.get_json()['message'] == expected_message
