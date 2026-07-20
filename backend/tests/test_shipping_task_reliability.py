from types import SimpleNamespace

import pytest
from flask import Flask

import services.shipping as shipping_module
import routes.shipping as shipping_routes


def _patch_common_shipping_import(monkeypatch, *, fail_insert=False):
    repository = shipping_module.shipping_repository
    calls = {'commit': 0, 'rollback': 0}

    monkeypatch.setattr(shipping_module, '_parse_csv_rows', lambda _content: [])
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


def test_finance_import_disables_chunk_commits_for_both_record_types(monkeypatch):
    repository = shipping_module.shipping_repository
    calls = {'commit': 0, 'rollback': 0, 'shipping_atomic': None, 'return_atomic': None}

    monkeypatch.setattr(
        shipping_module,
        '_parse_csv_finance_rows',
        lambda _content: ([], [], 0),
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


def test_sse_can_recover_terminal_state_after_worker_queue_is_lost(monkeypatch):
    app = Flask(__name__)
    shipping_routes._task_queues.clear()
    monkeypatch.setattr(shipping_routes.shipping_repository, 'get_task', lambda _task_id: _task())

    with app.test_request_context('/api/shipping/import/progress/task-1'):
        response = shipping_routes.import_progress('task-1')
        payload = response.get_data(as_text=True)

    assert '"step": "done"' in payload
    assert '"inserted": 3' in payload
