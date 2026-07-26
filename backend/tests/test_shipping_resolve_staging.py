from datetime import date, datetime, timedelta

import pytest
import sqlalchemy as sa
from flask import Flask

from database.base import db
from database.models.shipping import (
    ShippingOrderFinished,
    ShippingOrderFinishedNext,
    ShippingOrderFinishedGeneration,
    ShippingOrderFinishedGenerationNext,
    ShippingOrderFinishedStaging,
    ShippingResolveTarget,
    ShippingTask,
)
from database.repository.shipping import ShippingRepository
import services.shipping as shipping_module


def _app(database_path):
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{database_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        ShippingOrderFinished.__table__.create(db.engine)
        test_metadata = sa.MetaData()
        standby = ShippingOrderFinished.__table__.to_metadata(
            test_metadata,
            name=ShippingOrderFinishedNext.name,
        )
        # SQLite index names are database-global; MySQL index names are
        # table-scoped. These tests need identical columns, not duplicate
        # SQLite index objects.
        for index in list(standby.indexes):
            standby.indexes.remove(index)
        standby.create(db.engine)
        ShippingOrderFinishedGeneration.create(db.engine)
        ShippingOrderFinishedGenerationNext.create(db.engine)
        with db.engine.begin() as connection:
            connection.execute(
                db.insert(ShippingOrderFinishedGeneration).values(id=1)
            )
            connection.execute(
                db.insert(ShippingOrderFinishedGenerationNext).values(id=1)
            )
        ShippingTask.__table__.create(db.engine)
        ShippingResolveTarget.__table__.create(db.engine)
        ShippingOrderFinishedStaging.__table__.create(db.engine)
    return app


def _live(code='OLD', source='shipping'):
    return ShippingOrderFinished(
        ecommerce_order_no='ORDER-1',
        finished_code=code,
        finished_name=code,
        quantity=1,
        return_quantity=0,
        actual_quantity=1,
        shipped_date=date(2026, 7, 1),
        source=source,
    )


def _stage(task_id, code='NEW', source='shipping'):
    return ShippingOrderFinishedStaging(
        task_id=task_id,
        ecommerce_order_no='ORDER-1',
        finished_code=code,
        finished_name=code,
        quantity=1,
        return_quantity=0,
        actual_quantity=1,
        shipped_date=date(2026, 7, 25),
        source=source,
        is_stale=False,
    )


def _task(task_id):
    return ShippingTask(
        id=task_id,
        task_type='resolve_stale',
        status='committing',
        progress={},
        lease_key='shipping_mutation',
    )


def test_cancel_cleanup_leaves_live_generation_unchanged(tmp_path):
    app = _app(tmp_path / 'cancel.db')
    with app.app_context():
        db.session.add(_live())
        db.session.add(ShippingResolveTarget(
            task_id='task-cancel', source='shipping',
            ecommerce_order_no='ORDER-1',
        ))
        db.session.add(_stage('task-cancel'))
        db.session.commit()

        ShippingRepository.cleanup_resolve_staging('task-cancel')

        assert [
            row.finished_code for row in ShippingOrderFinished.query.all()
        ] == ['OLD']
        assert ShippingResolveTarget.query.count() == 0
        assert ShippingOrderFinishedStaging.query.count() == 0


def test_cleanup_retries_with_fresh_connections(tmp_path, monkeypatch):
    app = _app(tmp_path / 'cleanup-retry.db')
    with app.app_context():
        db.session.add(ShippingResolveTarget(
            task_id='task-retry', source='shipping',
            ecommerce_order_no='ORDER-1',
        ))
        db.session.add(_stage('task-retry'))
        db.session.commit()
        engine = db.engine
        real_connect = engine.connect
        attempts = 0

        def flaky_connect():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise RuntimeError('simulated broken pooled connection')
            return real_connect()

        monkeypatch.setattr(engine, 'connect', flaky_connect)

        ShippingRepository.cleanup_resolve_staging('task-retry')

        assert attempts >= 3
        assert ShippingResolveTarget.query.count() == 0
        assert ShippingOrderFinishedStaging.query.count() == 0


def test_subset_cutover_replaces_only_targeted_live_rows(tmp_path):
    app = _app(tmp_path / 'subset.db')
    with app.app_context():
        db.session.add_all([_live(), _live(code='FINANCE-OLD', source='finance')])
        db.session.add(ShippingResolveTarget(
            task_id='task-subset', source='shipping',
            ecommerce_order_no='ORDER-1',
        ))
        db.session.add(_stage('task-subset'))
        db.session.add(_task('task-subset'))
        db.session.commit()

        result = ShippingRepository.cutover_resolve_staging(
            'task-subset',
            full_rebuild=False,
            resolved_count=1,
            staged_rows=1,
        )

        rows = ShippingOrderFinished.query.order_by(
            ShippingOrderFinished.source,
        ).all()
        assert [(row.source, row.finished_code) for row in rows] == [
            ('finance', 'FINANCE-OLD'),
            ('shipping', 'NEW'),
        ]
        assert result == {
            'resolved': 1,
            'staged_rows': 1,
            'deleted_rows': 1,
            'inserted_rows': 1,
            'cleanup_pending': False,
        }
        task = db.session.get(ShippingTask, 'task-subset')
        assert task.status == 'done'
        assert task.lease_key is None
        assert task.result == result


def test_failed_cutover_rolls_back_delete_and_preserves_live_generation(tmp_path):
    app = _app(tmp_path / 'rollback.db')
    with app.app_context():
        db.session.add(_live())
        db.session.add(ShippingResolveTarget(
            task_id='task-fail', source='shipping',
            ecommerce_order_no='ORDER-1',
        ))
        db.session.add(_stage('task-fail', code='FAIL'))
        db.session.add(_task('task-fail'))
        db.session.commit()
        with db.engine.begin() as connection:
            connection.execute(sa.text("""
                CREATE TRIGGER reject_failed_generation
                BEFORE INSERT ON shipping_order_finished
                WHEN NEW.finished_code = 'FAIL'
                BEGIN
                    SELECT RAISE(ABORT, 'reject staged row');
                END
            """))

        with pytest.raises(sa.exc.IntegrityError):
            ShippingRepository.cutover_resolve_staging(
                'task-fail',
                full_rebuild=False,
                resolved_count=1,
                staged_rows=1,
            )

        db.session.expire_all()
        assert [
            row.finished_code for row in ShippingOrderFinished.query.all()
        ] == ['OLD']
        assert ShippingOrderFinishedStaging.query.count() == 1
        task = db.session.get(ShippingTask, 'task-fail')
        assert task.status == 'committing'
        assert task.lease_key == 'shipping_mutation'


def test_cutover_rejects_changed_task_state_and_rolls_back_live_rows(tmp_path):
    app = _app(tmp_path / 'state-race.db')
    with app.app_context():
        db.session.add(_live())
        db.session.add(ShippingResolveTarget(
            task_id='task-race', source='shipping',
            ecommerce_order_no='ORDER-1',
        ))
        db.session.add(_stage('task-race'))
        task = _task('task-race')
        task.status = 'interrupted'
        task.lease_key = None
        db.session.add(task)
        db.session.commit()

        with pytest.raises(RuntimeError, match='任务状态已变化'):
            ShippingRepository.cutover_resolve_staging(
                'task-race',
                full_rebuild=False,
                resolved_count=1,
                staged_rows=1,
            )

        db.session.expire_all()
        assert [
            row.finished_code for row in ShippingOrderFinished.query.all()
        ] == ['OLD']
        assert ShippingOrderFinishedStaging.query.count() == 1


def test_full_generation_rename_publishes_and_finishes_task(tmp_path):
    app = _app(tmp_path / 'full-rename.db')
    with app.app_context():
        db.session.add_all([_live(), _full_task('task-full')])
        db.session.commit()
        ShippingRepository.reset_full_resolve_generation('task-full')
        ShippingRepository.bulk_insert_order_finished_generation(
            'task-full',
            [{
                'ecommerce_order_no': 'ORDER-1',
                'finished_code': 'NEW',
                'finished_name': 'NEW',
                'quantity': 1,
                'return_quantity': 0,
                'actual_quantity': 1,
                'shipped_date': date(2026, 7, 25),
                'source': 'shipping',
                'resolved_at': datetime.now(),
            }],
        )

        result = ShippingRepository.publish_full_generation(
            'task-full',
            resolved_count=1,
            generation_rows=1,
        )

        db.session.remove()
        assert [
            row.finished_code for row in ShippingOrderFinished.query.all()
        ] == ['NEW']
        with db.engine.connect() as connection:
            retired_codes = connection.execute(
                db.select(ShippingOrderFinishedNext.c.finished_code)
            ).scalars().all()
            live_owner = connection.execute(
                db.select(
                    ShippingOrderFinishedGeneration.c.task_id
                ).where(ShippingOrderFinishedGeneration.c.id == 1)
            ).scalar_one()
        assert retired_codes == ['OLD']
        assert live_owner == 'task-full'
        task = db.session.get(ShippingTask, 'task-full')
        assert task.status == 'done'
        assert task.lease_key is None
        assert result['cutover'] == 'rename'
        assert result['retired_generation_retained'] is True
        assert result['deleted_rows'] == 1
        assert result['inserted_rows'] == 1


def test_startup_recovery_finishes_task_if_marker_was_published(tmp_path):
    app = _app(tmp_path / 'rename-recovery.db')
    with app.app_context():
        task = _full_task('task-recover')
        task.result = {
            'resolved': 1,
            'staged_rows': 1,
            'cutover': 'rename',
        }
        db.session.add_all([_live(), task])
        db.session.commit()
        ShippingRepository.reset_full_resolve_generation('task-recover')
        ShippingRepository.bulk_insert_order_finished_generation(
            'task-recover',
            [{
                'ecommerce_order_no': 'ORDER-1',
                'finished_code': 'RECOVERED',
                'finished_name': 'RECOVERED',
                'quantity': 1,
                'return_quantity': 0,
                'actual_quantity': 1,
                'source': 'shipping',
            }],
        )
        with db.engine.connect() as connection:
            ShippingRepository._rename_full_generation(connection)

        assert ShippingRepository.interrupt_running_tasks() == 0

        db.session.remove()
        recovered = db.session.get(ShippingTask, 'task-recover')
        assert recovered.status == 'done'
        assert recovered.result['cutover'] == 'rename'
        assert [
            row.finished_code for row in ShippingOrderFinished.query.all()
        ] == ['RECOVERED']


def test_retained_generation_can_be_atomically_rolled_back(tmp_path):
    app = _app(tmp_path / 'rename-rollback.db')
    with app.app_context():
        db.session.add_all([_live(), _full_task('task-rollback')])
        db.session.commit()
        ShippingRepository.reset_full_resolve_generation('task-rollback')
        ShippingRepository.bulk_insert_order_finished_generation(
            'task-rollback',
            [{
                'ecommerce_order_no': 'ORDER-1',
                'finished_code': 'NEW',
                'finished_name': 'NEW',
                'quantity': 1,
                'return_quantity': 0,
                'actual_quantity': 1,
                'source': 'shipping',
            }],
        )
        ShippingRepository.publish_full_generation(
            'task-rollback',
            resolved_count=1,
            generation_rows=1,
        )

        rollback = (
            ShippingRepository.rollback_published_full_generation(
                'task-rollback'
            )
        )

        db.session.remove()
        assert rollback['rolled_back'] is True
        assert [
            row.finished_code for row in ShippingOrderFinished.query.all()
        ] == ['OLD']
        with db.engine.connect() as connection:
            standby_codes = connection.execute(
                db.select(ShippingOrderFinishedNext.c.finished_code)
            ).scalars().all()
        assert standby_codes == ['NEW']


def test_mysql_generation_swap_is_one_atomic_rename_statement():
    statements = []

    class Dialect:
        name = 'mysql'

    class Connection:
        dialect = Dialect()

        def execute(self, statement):
            statements.append(str(statement))

    ShippingRepository._rename_full_generation(Connection())

    assert len(statements) == 1
    normalized = ' '.join(statements[0].split())
    assert normalized.startswith('RENAME TABLE')
    assert 'shipping_order_finished_next TO shipping_order_finished' in normalized
    assert (
        'shipping_order_finished_generation_next '
        'TO shipping_order_finished_generation'
    ) in normalized


def test_abandoned_staging_cleanup_is_delayed_and_scope_safe(tmp_path):
    app = _app(tmp_path / 'abandoned.db')
    with app.app_context():
        old_task = _task('task-old')
        old_task.status = 'interrupted'
        old_task.lease_key = None
        old_task.updated_at = datetime.now() - timedelta(hours=2)
        recent_task = _task('task-recent')
        recent_task.status = 'interrupted'
        recent_task.lease_key = None
        recent_task.updated_at = datetime.now()
        db.session.add_all([
            old_task,
            recent_task,
            ShippingResolveTarget(
                task_id='task-old', source='shipping',
                ecommerce_order_no='ORDER-1',
            ),
            ShippingResolveTarget(
                task_id='task-recent', source='shipping',
                ecommerce_order_no='ORDER-1',
            ),
            _stage('task-old', code='OLD-STAGE'),
            _stage('task-recent', code='RECENT-STAGE'),
        ])
        db.session.commit()

        ShippingRepository.cleanup_abandoned_resolve_staging()

        assert ShippingResolveTarget.query.filter_by(
            task_id='task-old',
        ).count() == 0
        assert ShippingOrderFinishedStaging.query.filter_by(
            task_id='task-old',
        ).count() == 0
        assert ShippingResolveTarget.query.filter_by(
            task_id='task-recent',
        ).count() == 1
        assert ShippingOrderFinishedStaging.query.filter_by(
            task_id='task-recent',
        ).count() == 1


def test_staged_service_losing_commit_cas_never_calls_cutover(monkeypatch):
    repository = shipping_module.shipping_repository
    calls = {'cleanup': 0, 'cutover': 0}
    monkeypatch.setattr(
        repository, 'cleanup_resolve_staging',
        lambda _task_id: calls.update(cleanup=calls['cleanup'] + 1),
    )
    monkeypatch.setattr(
        repository, 'cleanup_abandoned_resolve_staging',
        lambda: None,
    )


def _full_task(task_id):
    task = _task(task_id)
    task.task_type = 'resolve_all'
    return task
    monkeypatch.setattr(
        repository, 'reset_full_resolve_generation',
        lambda _task_id: None,
    )
    monkeypatch.setattr(
        repository, 'create_resolve_targets',
        lambda *_args, **_kwargs: 1,
    )
    monkeypatch.setattr(
        shipping_module, '_load_resolver_context',
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        shipping_module, '_resolve_orders',
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        repository, 'get_full_generation_stats',
        lambda _task_id: {
            'target_count': 1, 'staging_count': 1, 'orphan_count': 0,
        },
    )
    monkeypatch.setattr(
        repository, 'publish_full_generation',
        lambda *_args, **_kwargs: calls.update(cutover=1),
    )
    monkeypatch.setattr(shipping_module.db.session, 'rollback', lambda: None)

    with pytest.raises(InterruptedError, match='最终切换'):
        shipping_module.shipping_service._run_staged_resolve(
            'task-cas',
            [('ORDER-1', 'shipping')],
            full_rebuild=True,
            cancel_check=lambda: False,
            begin_commit=lambda: False,
        )

    assert calls == {'cleanup': 2, 'cutover': 0}


def test_cleanup_logging_keeps_original_signature(monkeypatch):
    repository = shipping_module.shipping_repository
    cleanup_calls = 0
    logged_contexts = []

    def cleanup(_task_id):
        nonlocal cleanup_calls
        cleanup_calls += 1
        if cleanup_calls == 2:
            raise RuntimeError('cleanup failed')

    monkeypatch.setattr(repository, 'cleanup_resolve_staging', cleanup)
    monkeypatch.setattr(
        repository, 'cleanup_abandoned_resolve_staging', lambda: None,
    )
    monkeypatch.setattr(
        repository, 'reset_full_resolve_generation', lambda _task_id: None,
    )
    monkeypatch.setattr(
        repository, 'create_resolve_targets',
        lambda *_args, **_kwargs: 1,
    )
    monkeypatch.setattr(
        shipping_module, '_load_resolver_context',
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        shipping_module, '_resolve_orders',
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        repository, 'get_full_generation_stats',
        lambda _task_id: {
            'target_count': 1,
            'staging_count': 1,
            'orphan_count': 0,
        },
    )
    monkeypatch.setattr(
        repository, 'publish_full_generation',
        lambda *_args, **_kwargs: {
            'resolved': 1,
            'staged_rows': 1,
            'deleted_rows': 1,
            'inserted_rows': 1,
            'cleanup_pending': False,
            'cutover': 'rename',
        },
    )
    monkeypatch.setattr(repository, 'update_task', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        shipping_module, 'report_internal_error',
        lambda context: logged_contexts.append(context) or 'error-id',
    )
    monkeypatch.setattr(shipping_module.db.session, 'remove', lambda: None)

    result = shipping_module.shipping_service._run_staged_resolve(
        'task-cleanup-log',
        [('ORDER-1', 'shipping')],
        full_rebuild=True,
        cancel_check=lambda: False,
        begin_commit=lambda: True,
    )

    assert result['cleanup_pending'] is True
    assert logged_contexts == [
        '清理重算暂存数据失败 task_id=task-cleanup-log',
    ]
