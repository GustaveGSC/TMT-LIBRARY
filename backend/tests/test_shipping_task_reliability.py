import io
from types import SimpleNamespace

import pytest
from flask import Flask

import services.shipping as shipping_module
import routes.shipping as shipping_routes


def _patch_common_shipping_import(monkeypatch, *, fail_insert=False):
    repository = shipping_module.shipping_repository
    calls = {'commit': 0, 'rollback': 0}

    monkeypatch.setattr(
        shipping_module, '_parse_csv_rows',
        lambda _content, **_kwargs: [],
    )
    monkeypatch.setattr(shipping_module, '_merge_rows', lambda rows: (rows, []))
    monkeypatch.setattr(repository, 'get_existing_keys', lambda *_args, **_kwargs: set())
    monkeypatch.setattr(
        repository,
        'create_batch',
        lambda *_args, **_kwargs: SimpleNamespace(id=17),
    )

    def bulk_insert(*_args, **kwargs):
        calls['commit_chunks'] = kwargs['commit_chunks']
        if fail_insert:
            raise RuntimeError('insert failed')
        return 0

    monkeypatch.setattr(repository, 'bulk_insert_shipping', bulk_insert)
    monkeypatch.setattr(repository, 'get_new_order_nos_by_source', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        shipping_module.db.session,
        'commit',
        lambda: calls.__setitem__('commit', calls['commit'] + 1),
    )
    monkeypatch.setattr(
        shipping_module.db.session,
        'rollback',
        lambda: calls.__setitem__('rollback', calls['rollback'] + 1),
    )
    return calls


def test_shipping_import_commits_once_after_all_work(monkeypatch):
    calls = _patch_common_shipping_import(monkeypatch)

    shipping_module.shipping_service.import_shipping('rows.csv', b'content')

    assert calls == {'commit': 1, 'rollback': 0, 'commit_chunks': False}


def test_shipping_import_keeps_derived_rows_in_same_transaction(monkeypatch):
    calls = _patch_common_shipping_import(monkeypatch)
    monkeypatch.setattr(
        shipping_module.shipping_repository,
        'get_new_order_nos_by_source',
        lambda *_args, **_kwargs: ['ORDER-1'],
    )
    monkeypatch.setattr(
        shipping_module,
        '_resolve_orders',
        lambda *_args, **kwargs: calls.__setitem__(
            'resolve_atomic', not kwargs['commit_chunks'],
        ),
    )

    shipping_module.shipping_service.import_shipping('rows.csv', b'content')

    assert calls['resolve_atomic'] is True
    assert calls['commit'] == 1


def test_shipping_import_rolls_back_without_cleanup_commit_on_failure(monkeypatch):
    calls = _patch_common_shipping_import(monkeypatch, fail_insert=True)

    with pytest.raises(RuntimeError, match='insert failed'):
        shipping_module.shipping_service.import_shipping('rows.csv', b'content')

    assert calls == {'commit': 0, 'rollback': 1, 'commit_chunks': False}


def test_csv_parser_checks_persisted_cancel_during_row_iteration():
    header = ','.join(shipping_module._REQUIRED_COL_NAMES)
    row = ','.join([
        'ORDER-1', '2026-07-24', '渠道', 'C001', '渠道商', '操作人',
        '1', 'P001', '产品', '1', '浙江省',
    ])
    content = ('\n'.join([header] + [row] * 501)).encode('utf-8')
    checks = {'count': 0}

    def cancel_check():
        checks['count'] += 1
        # 解析前、解码后、表头处各检查一次；第四次发生在第 500 行。
        return checks['count'] >= 4

    with pytest.raises(InterruptedError, match='用户已请求取消任务'):
        shipping_module._parse_csv_rows(content, cancel_check=cancel_check)

    assert checks['count'] == 4


def test_shipping_import_rolls_back_when_cancelled_during_insert(monkeypatch):
    calls = _patch_common_shipping_import(monkeypatch)

    def cancelled_insert(*_args, **kwargs):
        assert callable(kwargs['cancel_check'])
        raise InterruptedError('用户已请求取消任务')

    monkeypatch.setattr(
        shipping_module.shipping_repository,
        'bulk_insert_shipping',
        cancelled_insert,
    )

    with pytest.raises(InterruptedError, match='用户已请求取消任务'):
        shipping_module.shipping_service.import_shipping(
            'rows.csv', b'content', cancel_check=lambda: False,
        )

    assert calls['commit'] == 0
    assert calls['rollback'] == 1


def test_shipping_import_rolls_back_when_cancelled_during_resolve(monkeypatch):
    calls = _patch_common_shipping_import(monkeypatch)
    monkeypatch.setattr(
        shipping_module.shipping_repository,
        'get_new_order_nos_by_source',
        lambda *_args, **_kwargs: ['ORDER-1'],
    )

    def cancelled_resolve(*_args, **kwargs):
        assert kwargs['commit_chunks'] is False
        assert callable(kwargs['cancel_check'])
        raise InterruptedError('用户已请求取消任务')

    monkeypatch.setattr(shipping_module, '_resolve_orders', cancelled_resolve)

    with pytest.raises(InterruptedError, match='用户已请求取消任务'):
        shipping_module.shipping_service.import_shipping(
            'rows.csv', b'content', cancel_check=lambda: False,
        )

    assert calls['commit'] == 0
    assert calls['rollback'] == 1


def test_shipping_import_losing_final_commit_cas_rolls_back(monkeypatch):
    calls = _patch_common_shipping_import(monkeypatch)

    with pytest.raises(InterruptedError, match='最终提交'):
        shipping_module.shipping_service.import_shipping(
            'rows.csv',
            b'content',
            cancel_check=lambda: False,
            begin_commit=lambda: False,
        )

    assert calls['commit'] == 0
    assert calls['rollback'] == 1


def test_shipping_import_winning_final_commit_cas_commits_once(monkeypatch):
    calls = _patch_common_shipping_import(monkeypatch)
    order = []

    def begin_commit():
        order.append('cas')
        return True

    original_commit = shipping_module.db.session.commit

    def commit():
        order.append('commit')
        return original_commit()

    monkeypatch.setattr(shipping_module.db.session, 'commit', commit)

    shipping_module.shipping_service.import_shipping(
        'rows.csv',
        b'content',
        cancel_check=lambda: False,
        begin_commit=begin_commit,
    )

    assert order == ['cas', 'commit']
    assert calls['commit'] == 1
    assert calls['rollback'] == 0


def test_finance_import_disables_chunk_commits_for_both_record_types(monkeypatch):
    repository = shipping_module.shipping_repository
    calls = {'commit': 0, 'rollback': 0, 'shipping_atomic': None, 'return_atomic': None}

    monkeypatch.setattr(
        shipping_module,
        '_parse_csv_finance_rows',
        lambda _content, **_kwargs: ([], [], 0),
    )
    monkeypatch.setattr(shipping_module, '_merge_finance_shipping_rows', lambda rows: (rows, []))
    monkeypatch.setattr(shipping_module, '_merge_return_rows', lambda rows: (rows, []))
    monkeypatch.setattr(repository, 'get_existing_finance_keys', lambda _keys: set())
    monkeypatch.setattr(repository, 'get_existing_return_keys', lambda _keys: set())
    monkeypatch.setattr(
        repository,
        'create_batch',
        lambda *_args, **_kwargs: SimpleNamespace(id=18),
    )
    monkeypatch.setattr(
        repository,
        'bulk_insert_shipping',
        lambda *_args, **kwargs: calls.__setitem__('shipping_atomic', not kwargs['commit_chunks']) or 0,
    )
    monkeypatch.setattr(
        repository,
        'bulk_insert_return',
        lambda *_args, **kwargs: calls.__setitem__('return_atomic', not kwargs['commit_chunks']) or 0,
    )
    monkeypatch.setattr(repository, 'get_new_order_nos_by_source', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        shipping_module.db.session,
        'commit',
        lambda: calls.__setitem__('commit', calls['commit'] + 1),
    )
    monkeypatch.setattr(
        shipping_module.db.session,
        'rollback',
        lambda: calls.__setitem__('rollback', calls['rollback'] + 1),
    )

    shipping_module.shipping_service.import_finance('finance.csv', b'content')

    assert calls == {
        'commit': 1,
        'rollback': 0,
        'shipping_atomic': True,
        'return_atomic': True,
    }


def test_finance_import_propagates_cancel_and_honours_final_commit_cas(monkeypatch):
    repository = shipping_module.shipping_repository
    calls = {'commit': 0, 'rollback': 0, 'checks': 0}
    monkeypatch.setattr(
        shipping_module,
        '_parse_csv_finance_rows',
        lambda _content, **_kwargs: ([], [], 0),
    )
    monkeypatch.setattr(shipping_module, '_merge_finance_shipping_rows', lambda rows: (rows, []))
    monkeypatch.setattr(shipping_module, '_merge_return_rows', lambda rows: (rows, []))

    def shipping_snapshots(_keys, *, cancel_check):
        assert callable(cancel_check)
        calls['checks'] += 1
        return {}

    def return_snapshots(_keys, *, cancel_check):
        assert callable(cancel_check)
        calls['checks'] += 1
        return {}

    monkeypatch.setattr(repository, 'get_finance_shipping_snapshots', shipping_snapshots)
    monkeypatch.setattr(repository, 'get_finance_return_snapshots', return_snapshots)
    monkeypatch.setattr(
        repository, 'create_batch',
        lambda *_args, **_kwargs: SimpleNamespace(id=19),
    )
    monkeypatch.setattr(repository, 'bulk_insert_shipping', lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(repository, 'bulk_insert_return', lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(repository, 'get_new_order_nos_by_source', lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        shipping_module.db.session, 'commit',
        lambda: calls.__setitem__('commit', calls['commit'] + 1),
    )
    monkeypatch.setattr(
        shipping_module.db.session, 'rollback',
        lambda: calls.__setitem__('rollback', calls['rollback'] + 1),
    )

    with pytest.raises(InterruptedError, match='最终提交'):
        shipping_module.shipping_service.import_finance(
            'finance.csv',
            b'content',
            cancel_check=lambda: False,
            begin_commit=lambda: False,
        )

    assert calls == {'commit': 0, 'rollback': 1, 'checks': 2}


def _task(status='done'):
    data = {
        'task_id': 'task-1',
        'task_type': 'import_shipping',
        'status': status,
        'filename': 'rows.csv',
        'progress': {'step': status},
        'result': {'inserted': 3} if status == 'done' else None,
        'message': '',
        'created_at': '2026-07-20 16:00:00',
        'updated_at': '2026-07-20 16:01:00',
        'finished_at': '2026-07-20 16:01:00',
    }
    return SimpleNamespace(
        status=status,
        progress=data['progress'],
        result=data['result'],
        message=data['message'],
        updated_at=SimpleNamespace(isoformat=lambda: '2026-07-20T16:01:00'),
        to_dict=lambda: data,
    )


def test_status_endpoint_reads_persisted_terminal_state_without_memory_queue(monkeypatch):
    app = Flask(__name__)
    shipping_routes._task_queues.clear()
    monkeypatch.setattr(shipping_routes.shipping_repository, 'get_task', lambda _task_id: _task())

    with app.test_request_context('/api/shipping/import/status/task-1'):
        response, status_code = shipping_routes.get_import_task_status('task-1')

    assert status_code == 200
    assert response.get_json()['data']['status'] == 'done'
    assert response.get_json()['data']['result'] == {'inserted': 3}
    assert response.headers['Cache-Control'] == 'no-store'

    with app.test_request_context('/api/shipping/tasks/task-1'):
        canonical_response, canonical_status = (
            shipping_routes.get_persisted_task_status('task-1')
        )
    assert canonical_status == 200
    assert canonical_response.get_json() == response.get_json()
    assert canonical_response.headers['Cache-Control'] == 'no-store'


def test_new_tasks_do_not_allocate_unconsumed_sse_queues(monkeypatch):
    app = Flask(__name__)
    shipping_routes._task_queues.clear()
    monkeypatch.setattr(
        shipping_routes, '_check_file', lambda _file, _label: (b'content', None),
    )
    monkeypatch.setattr(
        shipping_routes, '_create_mutation_task',
        lambda *_args, **_kwargs: None,
    )

    started = []

    class FakeThread:
        def __init__(self, *, target, daemon):
            started.append((target, daemon))

        def start(self):
            return None

    monkeypatch.setattr(shipping_routes.threading, 'Thread', FakeThread)
    with app.test_request_context(
        '/api/shipping/import/finance',
        method='POST',
        data={'file': (io.BytesIO(b'content'), 'finance.csv')},
    ):
        response, status = shipping_routes.import_finance()

    assert status == 200
    assert response.get_json()['data']['task_id']
    assert started and started[0][1] is True
    assert shipping_routes._task_queues == {}


def test_persisted_progress_updates_do_not_require_memory_queue(monkeypatch):
    updates = []
    monkeypatch.setattr(
        shipping_routes.shipping_repository,
        'update_task',
        lambda task_id, **values: updates.append((task_id, values)),
    )

    shipping_routes._publish_task_event('task-1', None, 'inserting', current=2)
    shipping_routes._finish_task(
        'task-1', None, 'done', data={'inserted': 2},
    )

    assert updates == [
        ('task-1', {
            'status': 'running',
            'progress': {'step': 'inserting', 'current': 2},
        }),
        ('task-1', {
            'status': 'done',
            'progress': {'step': 'done', 'data': {'inserted': 2}},
            'result': {'inserted': 2},
            'message': '',
        }),
    ]


def test_sse_can_recover_terminal_state_after_worker_queue_is_lost(monkeypatch):
    app = Flask(__name__)
    shipping_routes._task_queues.clear()
    calls = {'get_task': 0}

    def get_task(_task_id):
        calls['get_task'] += 1
        return _task()

    monkeypatch.setattr(shipping_routes.shipping_repository, 'get_task', get_task)

    with app.test_request_context('/api/shipping/import/progress/task-1'):
        response = shipping_routes.import_progress('task-1')
        payload = response.get_data(as_text=True)

    assert calls['get_task'] == 1
    assert response.is_streamed is False
    assert response.headers['Cache-Control'] == 'no-store'
    assert '"step": "done"' in payload
    assert '"inserted": 3' in payload
