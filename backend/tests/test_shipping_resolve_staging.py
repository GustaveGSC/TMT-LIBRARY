from datetime import date, datetime, timedelta

import pytest
import sqlalchemy as sa
from flask import Flask

from database.base import db
from database.models.shipping import (
    ShippingOrderFinished,
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
        repository, 'get_resolve_staging_stats',
        lambda _task_id: {
            'target_count': 1, 'staging_count': 1, 'orphan_count': 0,
        },
    )
    monkeypatch.setattr(
        repository, 'cutover_resolve_staging',
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
