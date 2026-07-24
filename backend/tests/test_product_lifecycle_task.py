import threading
import uuid
from types import SimpleNamespace

from flask import Flask

from database.base import db
import database.models.product.category  # noqa: F401 需先注册 ProductModel 关系
import database.models.product.resource  # noqa: F401 注册成品-资料关联表
from database.models.product.lifecycle import ProductLifecycleTask
from database.repository.product.lifecycle import (
    ProductLifecycleTaskLeaseConflict,
    ProductLifecycleTaskRepository,
)
from routes.product import lifecycle as lifecycle_routes
from services.product import lifecycle as lifecycle_service


def _app(database_path):
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{database_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        ProductLifecycleTask.__table__.create(db.engine)
    return app


def test_database_lease_allows_only_one_lifecycle_task(tmp_path):
    app = _app(tmp_path / 'lifecycle-lease.db')
    barrier = threading.Barrier(2)
    outcomes = []
    lock = threading.Lock()

    def compete(task_id):
        with app.app_context():
            barrier.wait()
            try:
                ProductLifecycleTaskRepository.create_task(task_id)
                outcome = ('acquired', task_id)
            except ProductLifecycleTaskLeaseConflict as exc:
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


def test_reload_interrupts_task_and_releases_lifecycle_lease(tmp_path):
    app = _app(tmp_path / 'lifecycle-reload.db')
    first_id = str(uuid.uuid4())
    second_id = str(uuid.uuid4())

    with app.app_context():
        ProductLifecycleTaskRepository.create_task(first_id)
        assert ProductLifecycleTaskRepository.interrupt_running_tasks() == 1
        ProductLifecycleTaskRepository.create_task(second_id)

        first = db.session.get(ProductLifecycleTask, first_id)
        second = db.session.get(ProductLifecycleTask, second_id)
        assert first.status == 'interrupted'
        assert first.lease_key is None
        assert second.status == 'pending'


def test_conflicting_lifecycle_start_returns_409_with_task_id(monkeypatch):
    app = Flask(__name__)
    holder_id = str(uuid.uuid4())

    def reject(_task_id):
        raise ProductLifecycleTaskLeaseConflict(holder_id)

    monkeypatch.setattr(
        lifecycle_routes.product_lifecycle_task_repository,
        'create_task',
        reject,
    )
    with app.test_request_context('/api/product/lifecycle/update', method='POST'):
        response, status = lifecycle_routes.start_update()

    assert status == 409
    assert response.get_json() == {
        'success': False,
        'message': '已有产品生命周期更新任务正在运行，请等待其结束后重试',
        'data': {'task_id': holder_id},
    }


def test_task_endpoint_reads_persisted_state_without_sse(monkeypatch):
    app = Flask(__name__)
    task_data = {
        'task_id': 'task-1',
        'task_type': 'product_lifecycle',
        'status': 'done',
        'progress': {'step': 'done'},
        'result': {'updated': 2, 'total_models': 3},
        'message': '',
        'created_at': '2026-07-24 10:00:00',
        'updated_at': '2026-07-24 10:00:01',
        'finished_at': '2026-07-24 10:00:01',
    }
    task = SimpleNamespace(
        status='done',
        progress={'step': 'done'},
        result={'updated': 2, 'total_models': 3},
        message='',
        to_dict=lambda: task_data,
    )
    monkeypatch.setattr(
        lifecycle_routes.product_lifecycle_task_repository,
        'get_task',
        lambda _task_id: task,
    )

    with app.test_request_context('/api/product/lifecycle/tasks/task-1'):
        response, status = lifecycle_routes.get_task('task-1')

    assert status == 200
    assert response.get_json()['data']['status'] == 'done'
    assert response.headers['Cache-Control'] == 'no-store'

    with app.test_request_context('/api/product/lifecycle/progress/task-1'):
        legacy_response = lifecycle_routes.get_legacy_progress('task-1')

    assert legacy_response.is_streamed is False
    assert '"step": "done"' in legacy_response.get_data(as_text=True)
    assert legacy_response.headers['Cache-Control'] == 'no-store'


class _FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.hints = []

    def filter_by(self, **_kwargs):
        return self

    def join(self, *_args, **_kwargs):
        return self

    def with_hint(self, _model, hint, dialect_name=None):
        self.hints.append((hint, dialect_name))
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def group_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return self.rows


def test_lifecycle_uses_one_monthly_aggregate_and_one_commit(monkeypatch):
    operator_query = _FakeQuery([])
    monthly_query = _FakeQuery([
        SimpleNamespace(model_id=7, month='2024-01', total_qty=10),
        SimpleNamespace(model_id=7, month='2024-03', total_qty=5),
    ])
    finished = SimpleNamespace(
        model_id=7,
        market='domestic',
        listed_yymm=None,
        delisted_yymm=None,
        updated_at=None,
    )
    finished_query = _FakeQuery([finished])
    queries = iter((operator_query, monthly_query, finished_query))
    monkeypatch.setattr(
        lifecycle_service.db.session,
        'query',
        lambda *_args, **_kwargs: next(queries),
    )

    commits = []
    monkeypatch.setattr(
        lifecycle_service.db.session,
        'commit',
        lambda: commits.append(True),
    )
    monkeypatch.setattr(lifecycle_service, '_current_month', lambda: '2026-07')

    result = lifecycle_service.update_lifecycle()

    assert result == {'updated': 1, 'total_models': 1}
    assert finished.listed_yymm == '2023-12'
    assert finished.delisted_yymm == '2024-04'
    assert commits == [True]
    assert monthly_query.hints == [
        ('USE INDEX (ix_sof_finished_code_date)', 'mysql')
    ]
