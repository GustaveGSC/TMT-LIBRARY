import uuid
import queue
import threading
import json
from flask import Blueprint, request, Response, stream_with_context, current_app
from services.shipping import shipping_service
from result import Result

shipping_bp = Blueprint('shipping', __name__)

_ALLOWED_EXT = ('.xlsx', '.xls', '.csv')

# 进度队列：task_id → queue.Queue
_task_queues:  dict = {}
# 取消标志：task_id → bool
_cancel_flags: dict = {}


def _check_file(file, label: str):
    if not file:
        return None, Result.fail(f'未收到{label}文件').to_response()
    if not any(file.filename.lower().endswith(ext) for ext in _ALLOWED_EXT):
        return None, Result.fail(f'{label}文件格式不支持，请上传 .xlsx / .xls / .csv').to_response()
    return file.read(), None


@shipping_bp.post('/import/shipping')
def import_shipping():
    """接收文件，启动后台导入线程，返回 task_id 供前端订阅进度"""
    file = request.files.get('file')
    file_bytes, err = _check_file(file, '发货清单')
    if err:
        return err

    task_id  = str(uuid.uuid4())
    q        = queue.Queue()
    _task_queues[task_id]  = q
    _cancel_flags[task_id] = False
    filename = file.filename
    app      = current_app._get_current_object()

    def run():
        with app.app_context():
            try:
                def progress_cb(step, **kwargs):
                    q.put({'step': step, **kwargs})

                def cancel_check():
                    return _cancel_flags.get(task_id, False)

                result = shipping_service.import_shipping(
                    filename, file_bytes,
                    progress_cb=progress_cb,
                    cancel_check=cancel_check,
                )
                q.put({'step': 'done', 'data': result})
            except InterruptedError:
                q.put({'step': 'cancelled', 'message': '导入已中止'})
            except Exception as e:
                q.put({'step': 'error', 'message': str(e)})
            finally:
                _cancel_flags.pop(task_id, None)

    threading.Thread(target=run, daemon=True).start()
    return Result.ok(data={'task_id': task_id}).to_response()


@shipping_bp.post('/import/cancel/<task_id>')
def cancel_import(task_id):
    """设置取消标志，后台线程将在下一个 progress_cb 时中止"""
    _cancel_flags[task_id] = True
    return Result.ok(message='已发送中止信号').to_response()


@shipping_bp.get('/import/progress/<task_id>')
def import_progress(task_id):
    """SSE：流式推送导入进度事件直到 done / error"""
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
            if event.get('step') in ('done', 'error', 'cancelled'):
                _task_queues.pop(task_id, None)
                break

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@shipping_bp.get('/operators')
def get_operators():
    """获取所有操作人及其分类"""
    try:
        return Result.ok(data=shipping_service.get_operators()).to_response()
    except Exception as e:
        return Result.fail(str(e)).to_response()


@shipping_bp.post('/operators/classify')
def classify_operators():
    """批量设置操作人分类，body: [{ operator, type }]"""
    items = request.get_json(silent=True)
    if not isinstance(items, list):
        return Result.fail('请求体应为数组').to_response()
    try:
        result = shipping_service.classify_operators(items)
    except Exception as e:
        return Result.fail(str(e)).to_response()
    return Result.ok(data=result).to_response()


@shipping_bp.post('/resolve-all')
def resolve_all():
    """全量重新计算所有订单的成品组合（后台线程 + SSE 进度）"""
    task_id = str(uuid.uuid4())
    q       = queue.Queue()
    _task_queues[task_id] = q
    app = current_app._get_current_object()

    def run():
        with app.app_context():
            try:
                def progress_cb(step, **kwargs):
                    q.put({'step': step, **kwargs})
                result = shipping_service.resolve_all(progress_cb=progress_cb)
                q.put({'step': 'done', 'data': result})
            except Exception as e:
                q.put({'step': 'error', 'message': str(e)})

    threading.Thread(target=run, daemon=True).start()
    return Result.ok(data={'task_id': task_id}).to_response()


@shipping_bp.post('/resolve')
def resolve_stale():
    """手动刷新所有 is_stale 的成品组合"""
    try:
        result = shipping_service.resolve_stale()
    except Exception as e:
        return Result.fail(f'刷新失败：{str(e)}').to_response()
    return Result.ok(data=result).to_response()


@shipping_bp.get('/stats')
def get_stats():
    """看板统计摘要"""
    try:
        return Result.ok(data=shipping_service.get_stats()).to_response()
    except Exception as e:
        return Result.fail(str(e)).to_response()


@shipping_bp.get('/shipped-dates')
def get_shipped_dates():
    """返回所有已存在的 shipped_date 列表（去重升序）"""
    try:
        return Result.ok(data=shipping_service.get_shipped_dates()).to_response()
    except Exception as e:
        return Result.fail(str(e)).to_response()
