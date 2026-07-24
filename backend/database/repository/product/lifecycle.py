from datetime import timedelta

from sqlalchemy.exc import IntegrityError

from database.base import db
from database.models.product.lifecycle import ProductLifecycleTask
from utils import now_cst


class ProductLifecycleTaskLeaseConflict(Exception):
    """产品生命周期更新租约已被另一个任务持有。"""

    def __init__(self, task_id: str):
        super().__init__(task_id)
        self.task_id = task_id


class ProductLifecycleTaskRepository:
    LEASE_KEY = 'product_lifecycle_update'

    @staticmethod
    def create_task(task_id: str):
        now = now_cst()
        try:
            with db.engine.begin() as connection:
                connection.execute(
                    db.delete(ProductLifecycleTask).where(
                        ProductLifecycleTask.finished_at < now - timedelta(days=7)
                    )
                )
                connection.execute(db.insert(ProductLifecycleTask).values(
                    id=task_id,
                    status='pending',
                    progress={},
                    lease_key=ProductLifecycleTaskRepository.LEASE_KEY,
                    created_at=now,
                    updated_at=now,
                ))
        except IntegrityError:
            with db.engine.connect() as connection:
                holder = connection.execute(
                    db.select(ProductLifecycleTask.id).where(
                        ProductLifecycleTask.lease_key
                        == ProductLifecycleTaskRepository.LEASE_KEY
                    )
                ).scalar_one_or_none()
            if holder is None:
                raise
            raise ProductLifecycleTaskLeaseConflict(holder) from None

    @staticmethod
    def update_task(task_id: str, *, status=None, progress=None, result=None, message=None):
        values = {'updated_at': now_cst()}
        if status is not None:
            values['status'] = status
        if progress is not None:
            values['progress'] = progress
        if result is not None:
            values['result'] = result
        if message is not None:
            values['message'] = message
        if status in ('done', 'error', 'cancelled', 'interrupted'):
            values['finished_at'] = values['updated_at']
            values['lease_key'] = None
        with db.engine.begin() as connection:
            connection.execute(
                db.update(ProductLifecycleTask)
                .where(ProductLifecycleTask.id == task_id)
                .values(**values)
            )

    @staticmethod
    def get_task(task_id: str):
        # 每次短轮询开启新事务，避免 MySQL REPEATABLE READ 看不到终态。
        db.session.remove()
        task = db.session.get(ProductLifecycleTask, task_id)
        if task is not None:
            db.session.expunge(task)
        db.session.remove()
        return task

    @staticmethod
    def interrupt_running_tasks():
        """新 worker 启动时标记上一进程未完成的生命周期任务。"""
        now = now_cst()
        with db.engine.begin() as connection:
            result = connection.execute(
                db.update(ProductLifecycleTask)
                .where(ProductLifecycleTask.status.in_(('pending', 'running')))
                .values(
                    status='interrupted',
                    message='任务因服务重启或重载中断，生命周期数据已回滚',
                    updated_at=now,
                    finished_at=now,
                    lease_key=None,
                )
            )
        return result.rowcount


product_lifecycle_task_repository = ProductLifecycleTaskRepository()
