import threading
import uuid

from flask import Flask

from database.base import db
from database.models.shipping import ShippingTask
from database.repository.shipping import (
    ShippingRepository,
    ShippingTaskLeaseConflict,
)
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


def test_database_lease_allows_only_one_concurrent_shipping_mutation(tmp_path):
    app = _app(tmp_path / 'lease.db')
    barrier = threading.Barrier(2)
    outcomes = []
    lock = threading.Lock()

    def compete(task_id):
        with app.app_context():
            barrier.wait()
            try:
                ShippingRepository.create_task(
                    task_id, 'import_shipping', lease_key=LEASE_KEY,
                )
                outcome = ('acquired', task_id)
            except ShippingTaskLeaseConflict as exc:
                outcome = ('blocked', exc.task_id)
            finally:
                db.session.remove()
            with lock:
                outcomes.append(outcome)

    task_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    threads = [threading.Thread(target=compete, args=(task_id,)) for task_id in task_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    acquired = [value for status, value in outcomes if status == 'acquired']
    blocked = [value for status, value in outcomes if status == 'blocked']
    assert len(acquired) == 1
    assert blocked == acquired


def test_reload_recovery_interrupts_holder_and_releases_lease(tmp_path):
    app = _app(tmp_path / 'recovery.db')
    first_id = str(uuid.uuid4())
    second_id = str(uuid.uuid4())

    with app.app_context():
        ShippingRepository.create_task(
            first_id, 'import_finance', lease_key=LEASE_KEY,
        )

        assert ShippingRepository.interrupt_running_tasks() == 1

        ShippingRepository.create_task(
            second_id, 'resolve_all', lease_key=LEASE_KEY,
        )
        first = db.session.get(ShippingTask, first_id)
        second = db.session.get(ShippingTask, second_id)
        assert first.status == 'interrupted'
        assert first.lease_key is None
        assert second.status == 'pending'
        assert second.lease_key == LEASE_KEY


def test_terminal_task_update_releases_lease(tmp_path):
    app = _app(tmp_path / 'terminal.db')
    first_id = str(uuid.uuid4())
    second_id = str(uuid.uuid4())

    with app.app_context():
        ShippingRepository.create_task(
            first_id, 'resolve_stale', lease_key=LEASE_KEY,
        )
        ShippingRepository.update_task(first_id, status='done')
        ShippingRepository.create_task(
            second_id, 'import_shipping', lease_key=LEASE_KEY,
        )

        assert db.session.get(ShippingTask, first_id).lease_key is None
        assert db.session.get(ShippingTask, second_id).lease_key == LEASE_KEY


def test_conflicting_route_task_returns_409_with_current_task_id(monkeypatch):
    app = Flask(__name__)
    holder_id = str(uuid.uuid4())

    def reject(*_args, **_kwargs):
        raise ShippingTaskLeaseConflict(holder_id)

    monkeypatch.setattr(shipping_routes.shipping_repository, 'create_task', reject)
    with app.app_context():
        response, status = shipping_routes._create_mutation_task(
            str(uuid.uuid4()), 'resolve_all',
        )

    assert status == 409
    assert response.get_json() == {
        'success': False,
        'message': '已有发货数据任务正在运行，请等待其结束后重试',
        'data': {'task_id': holder_id},
    }
