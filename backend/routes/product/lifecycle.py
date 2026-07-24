import threading
import uuid
import json

from flask import Blueprint, Response, current_app

from auth import make_blueprint_guard
from database.base import db
from database.repository.product.lifecycle import (
    ProductLifecycleTaskLeaseConflict,
    product_lifecycle_task_repository,
)
from error_handling import internal_task_error
from result import Result


lifecycle_bp = Blueprint('lifecycle', __name__)
_guard = make_blueprint_guard('product:view', 'product:edit')


@lifecycle_bp.before_request
def _lifecycle_guard():
    return _guard()


@lifecycle_bp.post('/update')
def start_update():
    """启动持久化生命周期更新任务。"""
    task_id = str(uuid.uuid4())
    try:
        product_lifecycle_task_repository.create_task(task_id)
    except ProductLifecycleTaskLeaseConflict as exc:
        return Result.fail(
            '已有产品生命周期更新任务正在运行，请等待其结束后重试',
            data={'task_id': exc.task_id},
        ).to_response(409)

    app = current_app._get_current_object()

    def run():
        with app.app_context():
            try:
                from services.product.lifecycle import update_lifecycle

                product_lifecycle_task_repository.update_task(
                    task_id,
                    status='running',
                    progress={'step': 'preparing', 'current': 0, 'total': 0},
                )

                def progress_cb(step, **kwargs):
                    product_lifecycle_task_repository.update_task(
                        task_id,
                        status='running',
                        progress={'step': step, **kwargs},
                    )

                result = update_lifecycle(progress_cb=progress_cb)
                product_lifecycle_task_repository.update_task(
                    task_id,
                    status='done',
                    progress={'step': 'done', 'data': result},
                    result=result,
                    message='',
                )
            except Exception:
                db.session.rollback()
                product_lifecycle_task_repository.update_task(
                    task_id,
                    status='error',
                    progress={'step': 'error'},
                    message=internal_task_error('产品生命周期更新失败'),
                )
            finally:
                db.session.remove()

    threading.Thread(target=run, daemon=True).start()
    return Result.ok(data={'task_id': task_id}).to_response()


@lifecycle_bp.get('/tasks/<task_id>')
def get_task(task_id):
    """短轮询读取生命周期任务的持久化状态。"""
    task = product_lifecycle_task_repository.get_task(task_id)
    if task is None:
        response, status = Result.fail('任务不存在').to_response(404)
    else:
        response, status = Result.ok(data=task.to_dict()).to_response()
    response.headers['Cache-Control'] = 'no-store'
    return response, status


@lifecycle_bp.get('/progress/<task_id>')
def get_legacy_progress(task_id):
    """旧前端兼容：立即返回一次持久化快照，不保持 SSE 长连接。"""
    task = product_lifecycle_task_repository.get_task(task_id)
    if task is None:
        return Result.fail('任务不存在').to_response(404)

    payload = dict(task.progress or {})
    if task.status == 'done':
        payload = {'step': 'done', 'data': task.result or {}}
    elif task.status in ('error', 'cancelled', 'interrupted'):
        payload = {
            'step': 'error',
            'message': task.message or '任务未完成',
        }
    else:
        payload.setdefault('step', 'preparing')

    return Response(
        f'data: {json.dumps(payload, ensure_ascii=False)}\n\n',
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-store',
            'X-Accel-Buffering': 'no',
        },
    )
