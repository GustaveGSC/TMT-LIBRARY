import uuid
import queue
import threading
import json
from flask import Blueprint, Response, stream_with_context, current_app
from result import Result

lifecycle_bp = Blueprint('lifecycle', __name__)

# 进度队列：task_id → queue.Queue
_task_queues: dict = {}


@lifecycle_bp.post('/update')
def start_update():
    """启动生命周期批量更新任务，返回 task_id 供前端订阅进度"""
    task_id = str(uuid.uuid4())
    q = queue.Queue()
    _task_queues[task_id] = q
    app = current_app._get_current_object()

    def run():
        with app.app_context():
            try:
                from services.product.lifecycle import update_lifecycle

                def progress_cb(step, **kwargs):
                    q.put({'step': step, **kwargs})

                result = update_lifecycle(progress_cb=progress_cb)
                q.put({'step': 'done', 'data': result})
            except Exception as e:
                q.put({'step': 'error', 'message': str(e)})

    threading.Thread(target=run, daemon=True).start()
    return Result.ok(data={'task_id': task_id}).to_response()


@lifecycle_bp.get('/progress/<task_id>')
def get_progress(task_id):
    """SSE：流式推送生命周期更新进度直到 done / error"""
    q = _task_queues.get(task_id)
    if not q:
        return Result.fail('任务不存在').to_response()

    def generate():
        while True:
            try:
                event = q.get(timeout=300)
            except queue.Empty:
                payload = {'step': 'error', 'message': '处理超时'}
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                _task_queues.pop(task_id, None)
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event.get('step') in ('done', 'error'):
                _task_queues.pop(task_id, None)
                break

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )
