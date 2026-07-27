import os
import uuid
import threading
import json
from flask import Blueprint, request, Response, current_app, g
from services.shipping import (
    ShippingRuleChangeConflict, StaleResolveScopeTooLarge, shipping_service,
)
from auth import make_blueprint_guard
from result import Result
from database.base import db
from database.repository.shipping import (
    ShippingTaskLeaseConflict,
    shipping_repository,
    _invalidate_chart_options_cache,
)
from upload_validation import read_spreadsheet_upload, UploadValidationError
from error_handling import internal_error_response, internal_task_error

shipping_bp = Blueprint('shipping', __name__)

# SSE 进度端点由 EventSource 发起，浏览器不支持携带自定义 Header，
# 用 task_id（UUID）作为访问凭证，从 before_request 中豁免。
_SSE_ENDPOINTS = frozenset({'shipping.import_progress'})

_VIEW_POST = ('/chart-data',)


def _is_full_resolve_enabled():
    return os.getenv('ALLOW_FULL_RESOLVE', '').strip().lower() in {
        '1', 'true', 'yes', 'on',
    }


def _shipping_guard():
    if request.endpoint in _SSE_ENDPOINTS:
        return None
    return make_blueprint_guard(
        'shipping:view', 'shipping:edit', 'shipping:export',
        view_post_paths=_VIEW_POST,
    )()

shipping_bp.before_request(_shipping_guard)

# 旧版 SSE 兼容状态；新任务不再创建内存队列，进度以数据库为唯一来源。
_task_queues:  dict = {}
_MUTATION_LEASE_KEY = 'shipping_data_mutation'


def _create_mutation_task(task_id, task_type, filename=None):
    try:
        shipping_repository.create_task(
            task_id, task_type, filename, lease_key=_MUTATION_LEASE_KEY,
        )
    except ShippingTaskLeaseConflict as exc:
        return Result.fail(
            '已有发货数据任务正在运行，请等待其结束后重试',
            data={'task_id': exc.task_id},
        ).to_response(409)
    return None


def _check_file(file, label: str):
    if not file:
        return None, Result.fail(f'未收到{label}文件').to_response()
    try:
        return read_spreadsheet_upload(
            file, label=label, allow_csv=True,
        ), None
    except UploadValidationError as exc:
        return None, Result.fail(str(exc)).to_response(413 if '不能超过' in str(exc) else 400)


def _publish_task_event(task_id: str, q, step: str, **kwargs):
    event = {'step': step, **kwargs}
    if q is not None:
        q.put(event)
    shipping_repository.update_task(
        task_id,
        status='running',
        progress=event,
    )


def _finish_task(task_id: str, q, status: str, *, data=None, message=''):
    step = status if status != 'interrupted' else 'error'
    event = {'step': step}
    if data is not None:
        event['data'] = data
    if message:
        event['message'] = message
    if q is not None:
        q.put(event)
    shipping_repository.update_task(
        task_id,
        status=status,
        progress=event,
        result=data,
        message=message,
    )


@shipping_bp.post('/import/shipping')
def import_shipping():
    """接收文件，启动后台导入线程，返回 task_id 供前端订阅进度"""
    file = request.files.get('file')
    file_bytes, err = _check_file(file, '发货清单')
    if err:
        return err

    task_id  = str(uuid.uuid4())
    conflict = _create_mutation_task(task_id, 'import_shipping', file.filename)
    if conflict:
        return conflict
    q = None
    filename = file.filename
    app      = current_app._get_current_object()

    def run():
        with app.app_context():
            try:
                def progress_cb(step, **kwargs):
                    _publish_task_event(task_id, q, step, **kwargs)

                def cancel_check():
                    return shipping_repository.is_cancel_requested(task_id)

                def begin_commit():
                    return shipping_repository.try_begin_commit(task_id)

                result = shipping_service.import_shipping(
                    filename, file_bytes,
                    progress_cb=progress_cb,
                    cancel_check=cancel_check,
                    begin_commit=begin_commit,
                )
                _invalidate_chart_options_cache()
                _finish_task(task_id, q, 'done', data=result)
            except InterruptedError:
                _finish_task(task_id, q, 'cancelled', message='导入已中止，业务数据已回滚')
            except Exception:
                _finish_task(task_id, q, 'error', message=internal_task_error('发货数据导入失败'))
            finally:
                db.session.remove()

    threading.Thread(target=run, daemon=True).start()
    return Result.ok(data={'task_id': task_id}).to_response()


@shipping_bp.post('/import/finance')
def import_finance():
    """接收财务清单，启动后台导入线程，返回 task_id 供前端订阅进度"""
    file = request.files.get('file')
    file_bytes, err = _check_file(file, '财务清单')
    if err:
        return err

    task_id  = str(uuid.uuid4())
    conflict = _create_mutation_task(task_id, 'import_finance', file.filename)
    if conflict:
        return conflict
    q = None
    filename = file.filename
    app      = current_app._get_current_object()

    def run():
        with app.app_context():
            try:
                def progress_cb(step, **kwargs):
                    _publish_task_event(task_id, q, step, **kwargs)

                def cancel_check():
                    return shipping_repository.is_cancel_requested(task_id)

                def begin_commit():
                    return shipping_repository.try_begin_commit(task_id)

                result = shipping_service.import_finance(
                    filename, file_bytes,
                    progress_cb=progress_cb,
                    cancel_check=cancel_check,
                    begin_commit=begin_commit,
                )
                _invalidate_chart_options_cache()
                _finish_task(task_id, q, 'done', data=result)
            except InterruptedError:
                _finish_task(task_id, q, 'cancelled', message='导入已中止，业务数据已回滚')
            except Exception:
                _finish_task(task_id, q, 'error', message=internal_task_error('财务数据导入失败'))
            finally:
                db.session.remove()

    threading.Thread(target=run, daemon=True).start()
    return Result.ok(data={'task_id': task_id}).to_response()


@shipping_bp.post('/import/cancel/<task_id>')
def cancel_import(task_id):
    """旧客户端兼容入口，转发到统一持久化取消协议。"""
    return _cancel_task_response(task_id)


@shipping_bp.post('/tasks/<task_id>/cancel')
def cancel_task(task_id):
    """原子登记持久化取消请求；worker 在安全检查点进入 cancelled。"""
    return _cancel_task_response(task_id)


def _cancel_task_response(task_id):
    outcome, task = shipping_repository.request_task_cancel(
        task_id,
        requested_by=g.current_user.get('id'),
    )
    if outcome == 'not_found':
        return Result.fail('任务不存在').to_response(404)
    if outcome == 'unsupported':
        return Result.fail('该任务暂不支持取消', data=task).to_response()
    if outcome == 'committing':
        return Result.fail(
            '任务正在提交最终结果，已无法取消',
            data=task,
        ).to_response(409)
    if outcome == 'finished':
        return Result.fail('任务已经结束，无法取消', data=task).to_response()

    message = '已发送取消请求'
    return Result.ok(data=task, message=message).to_response()


@shipping_bp.get('/import/progress/<task_id>')
def import_progress(task_id):
    """旧前端兼容：立即返回一次持久化快照，不保持 SSE 长连接。"""
    task = shipping_repository.get_task(task_id)
    if not task:
        return Result.fail('任务不存在').to_response(404)

    event = dict(task.progress or {})
    event.setdefault('step', task.status)
    if task.status == 'done':
        event['step'] = 'done'
        event['data'] = task.result
    elif task.status in ('error', 'cancelled', 'interrupted'):
        event['step'] = 'cancelled' if task.status == 'cancelled' else 'error'
        event['message'] = task.message or '任务因服务重载中断'

    return Response(
        f"data: {json.dumps(event, ensure_ascii=False)}\n\n",
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'},
    )


@shipping_bp.get('/operators')
def get_operators():
    """获取所有操作人及其分类"""
    try:
        return Result.ok(data=shipping_service.get_operators()).to_response()
    except Exception:
        return internal_error_response('查询发货操作人失败')


@shipping_bp.post('/operators/classify')
def classify_operators():
    """批量设置操作人分类，body: [{ operator, type }]"""
    items = request.get_json(silent=True)
    if not isinstance(items, list):
        return Result.fail('请求体应为数组').to_response()
    try:
        result = shipping_service.classify_operators(items)
    except Exception:
        return internal_error_response('保存发货操作人分类失败')
    return Result.ok(data=result).to_response()


@shipping_bp.post('/resolve-all')
def resolve_all():
    """全量重新计算所有订单的成品组合（后台线程 + SSE 进度）"""
    if not _is_full_resolve_enabled():
        return Result.fail(
            '全量重建正在维护优化，当前暂不可用'
        ).to_response(503)

    task_id = str(uuid.uuid4())
    conflict = _create_mutation_task(task_id, 'resolve_all')
    if conflict:
        return conflict
    q = None
    app = current_app._get_current_object()

    def run():
        with app.app_context():
            try:
                def progress_cb(step, **kwargs):
                    _publish_task_event(task_id, q, step, **kwargs)

                def cancel_check():
                    return shipping_repository.is_cancel_requested(task_id)

                def begin_commit():
                    return shipping_repository.try_begin_commit(task_id)

                shipping_service.resolve_all(
                    task_id,
                    progress_cb=progress_cb,
                    cancel_check=cancel_check,
                    begin_commit=begin_commit,
                )
            except InterruptedError:
                _finish_task(
                    task_id, q, 'cancelled',
                    message='重算已取消，线上数据保持不变',
                )
            except Exception:
                _finish_task(task_id, q, 'error', message=internal_task_error('发货数据重算失败'))
            else:
                # Publication and task completion were committed atomically.
                # Cache maintenance must not overwrite that terminal state.
                _invalidate_chart_options_cache()
            finally:
                db.session.remove()

    threading.Thread(target=run, daemon=True).start()
    return Result.ok(data={'task_id': task_id}).to_response()


def _persisted_task_status_response(task_id):
    task = shipping_repository.get_task(task_id)
    if not task:
        return Result.fail('任务不存在').to_response(404)
    response, status = Result.ok(data=task.to_dict()).to_response()
    response.headers['Cache-Control'] = 'no-store'
    return response, status


@shipping_bp.get('/tasks/<task_id>')
def get_persisted_task_status(task_id):
    """Canonical short-polling endpoint for all shipping background tasks."""
    return _persisted_task_status_response(task_id)


@shipping_bp.get('/import/status/<task_id>')
def get_import_task_status(task_id):
    """Compatibility alias for the canonical persisted task endpoint."""
    return _persisted_task_status_response(task_id)


@shipping_bp.post('/resolve')
def resolve_stale():
    """手动刷新所有 is_stale 的成品组合（后台线程，立即返回 task_id）"""
    task_id = str(uuid.uuid4())
    conflict = _create_mutation_task(task_id, 'resolve_stale')
    if conflict:
        return conflict
    app = current_app._get_current_object()

    def run():
        with app.app_context():
            try:
                def progress_cb(step, **kwargs):
                    _publish_task_event(task_id, None, step, **kwargs)

                def cancel_check():
                    return shipping_repository.is_cancel_requested(task_id)

                def begin_commit():
                    return shipping_repository.try_begin_commit(task_id)

                shipping_service.resolve_stale(
                    task_id,
                    progress_cb=progress_cb,
                    cancel_check=cancel_check,
                    begin_commit=begin_commit,
                )
            except InterruptedError:
                _finish_task(
                    task_id, None, 'cancelled',
                    message='重算已取消，线上数据保持不变',
                )
            except StaleResolveScopeTooLarge as exc:
                _finish_task(
                    task_id, None, 'error',
                    message=str(exc),
                )
            except Exception:
                _finish_task(
                    task_id, None, 'error',
                    message=internal_task_error('旧数据迁移失败'),
                )
            else:
                _invalidate_chart_options_cache()
            finally:
                db.session.remove()

    threading.Thread(target=run, daemon=True).start()
    return Result.ok(data={'task_id': task_id}).to_response()


@shipping_bp.get('/task-status/<task_id>')
def get_task_status(task_id):
    """兼容旧前端的轮询入口，底层读取持久化任务状态。"""
    task = shipping_repository.get_task(task_id)
    if not task:
        return Result.fail('任务不存在').to_response(404)
    data = task.to_dict()
    # 兼容旧接口用 data 字段承载任务结果。
    data['data'] = data.pop('result')
    return Result.ok(data=data).to_response()


@shipping_bp.get('/stats')
def get_stats():
    """看板统计摘要"""
    try:
        return Result.ok(data=shipping_service.get_stats()).to_response()
    except Exception:
        return internal_error_response('查询发货统计失败')


@shipping_bp.get('/shipped-dates')
def get_shipped_dates():
    """返回所有已存在的 shipped_date 列表（去重升序）"""
    try:
        return Result.ok(data=shipping_service.get_shipped_dates()).to_response()
    except Exception:
        return internal_error_response('查询发货日期失败')


@shipping_bp.get('/warehouses')
def get_warehouses():
    """返回所有出现过的仓库名及是否排除状态"""
    try:
        return Result.ok(data=shipping_service.get_warehouses()).to_response()
    except Exception:
        return internal_error_response('查询仓库配置失败')


@shipping_bp.post('/warehouses/filter')
def save_warehouse_filters():
    """批量保存仓库过滤配置，body: [{ warehouse_name, is_excluded }]"""
    items = request.get_json(silent=True)
    if not isinstance(items, list):
        return Result.fail('请求体应为数组').to_response()
    try:
        result = shipping_service.save_warehouse_filters(items)
    except ShippingRuleChangeConflict as exc:
        return Result.fail(
            '已有发货数据任务正在运行，请等待其结束后重试',
            data={'task_id': exc.task_id},
        ).to_response(409)
    except Exception:
        return internal_error_response('保存仓库配置失败')
    return Result.ok(data=result).to_response()


@shipping_bp.get('/finance-customer-aliases')
def get_finance_customer_aliases():
    keyword = (request.args.get('keyword') or '').strip() or None
    status = (request.args.get('status') or '').strip() or None
    if status not in (None, 'pending', 'export', 'domestic', 'non_sales'):
        return Result.fail('status 必须是 pending、export、domestic、non_sales 之一').to_response()
    page = max(request.args.get('page', 1, type=int), 1)
    per_page = min(max(request.args.get('per_page', 100, type=int), 1), 500)
    try:
        data = shipping_service.get_finance_customer_aliases(keyword, status, page, per_page)
        return Result.ok(data=data).to_response()
    except Exception:
        return internal_error_response('查询财务客户简称失败')


@shipping_bp.post('/finance-customer-aliases/mapping')
def save_finance_customer_mapping():
    try:
        data = shipping_service.save_finance_customer_mapping(request.get_json() or {})
        _invalidate_chart_options_cache()
        return Result.ok(data=data, message='保存成功').to_response()
    except ValueError as exc:
        return Result.fail(str(exc)).to_response()
    except Exception:
        return internal_error_response('保存财务客户映射失败')


@shipping_bp.get('/orders')
def get_orders():
    """分页查询 shipping_order_finished，支持筛选和排序"""
    page       = max(1, int(request.args.get('page', 1)))
    size       = min(200, max(1, int(request.args.get('size', 50))))
    sort_field = request.args.get('sort_field', 'shipped_date')
    sort_order = request.args.get('sort_order', 'desc')

    filters = {
        'ecommerce_order_no': request.args.get('ecommerce_order_no', '').strip(),
        'finished_code':      request.args.get('finished_code', '').strip(),
        'finished_name':      request.args.get('finished_name', '').strip(),
        'category_name':      request.args.get('category_name', '').strip(),
        'series_code':        request.args.get('series_code', '').strip(),
        'model_code':         request.args.get('model_code', '').strip(),
        'channel_name':       request.args.get('channel_name', '').strip(),
        'channel_code':       request.args.get('channel_code', '').strip(),
        'channel_org_name':   request.args.get('channel_org_name', '').strip(),
        'province':           request.args.get('province', '').strip(),
        'city':               request.args.get('city', '').strip(),
        'district':           request.args.get('district', '').strip(),
        'date_start':         request.args.get('date_start', '').strip(),
        'date_end':           request.args.get('date_end', '').strip(),
    }
    try:
        return Result.ok(data=shipping_service.get_orders(page, size, filters, sort_field, sort_order)).to_response()
    except Exception:
        return internal_error_response('查询发货订单失败')


@shipping_bp.get('/product/<string:code>/monthly')
def get_product_monthly(code):
    """返回指定成品编码按月聚合的发货/销退/实际数量"""
    try:
        source = request.args.get('source', 'shipping')
        if source not in ('shipping', 'finance'):
            source = 'shipping'
        return shipping_service.get_product_monthly(code, source=source).to_response()
    except Exception:
        return internal_error_response('查询产品月度发货数据失败')


@shipping_bp.get('/chart-options')
def get_chart_options():
    """返回渠道、省份、活跃产品 ID，按日期范围过滤（date_start/date_end 查询参数可选）"""
    date_start = request.args.get('date_start')
    date_end   = request.args.get('date_end')
    source     = request.args.get('source', 'shipping')
    try:
        return Result.ok(data=shipping_service.get_chart_options(date_start, date_end, source=source)).to_response()
    except Exception:
        return internal_error_response('查询发货图表选项失败')


@shipping_bp.post('/chart-data')
def get_chart_data():
    """
    POST body: { group_by, date_start?, date_end?, channel_names?, provinces?,
                 category_id?, series_id?, model_id? }
    返回 { summary: {quantity, return_quantity, actual_quantity},
            items: [{label, quantity, return_quantity, actual_quantity}] }
    """
    import re
    params = request.get_json(silent=True) or {}
    gb = params.get('group_by')
    valid_fixed = {'date', 'category', 'series', 'model', 'channel', 'channel_code', 'province', 'city', 'district'}
    if not (gb in valid_fixed or (isinstance(gb, str) and re.match(r'^tag:\d+$', gb))):
        params['group_by'] = 'date'
    try:
        return Result.ok(data=shipping_service.get_chart_data(params)).to_response()
    except Exception:
        return internal_error_response('查询发货图表数据失败')


# ── 产成品通用件配置 ──────────────────────────────────────

@shipping_bp.get('/equivalents')
def list_equivalents():
    """列出所有通用件对（含产成品名称）"""
    from database.models.product.finished import PackagedEquivalent, ProductPackaged
    from database.base import db
    pairs = PackagedEquivalent.query.order_by(PackagedEquivalent.created_at.desc()).all()
    # 批量取产成品名称
    codes = set()
    for p in pairs:
        codes.update([p.code_a, p.code_b])
    name_map = {}
    if codes:
        rows = ProductPackaged.query.filter(ProductPackaged.code.in_(codes)).all()
        name_map = {r.code: r.name for r in rows}
    result = []
    for p in pairs:
        d = p.to_dict()
        d['name_a'] = name_map.get(p.code_a, '')
        d['name_b'] = name_map.get(p.code_b, '')
        result.append(d)
    return Result.ok(result).to_response()


@shipping_bp.post('/equivalents')
def add_equivalent():
    """新增通用件对。body: {code_a, code_b, note?}"""
    body = request.get_json(silent=True) or {}
    code_a = str(body.get('code_a', '')).strip()
    code_b = str(body.get('code_b', '')).strip()
    note   = str(body.get('note', '')).strip() or None
    try:
        data = shipping_service.add_equivalent(code_a, code_b, note)
    except ShippingRuleChangeConflict as exc:
        return Result.fail('已有发货数据任务正在运行，请等待其结束后重试', data={'task_id': exc.task_id}).to_response(409)
    except ValueError as exc:
        return Result.fail(str(exc)).to_response()
    except Exception:
        return internal_error_response('保存通用件对失败')
    return Result.ok(data).to_response()


@shipping_bp.delete('/equivalents/<int:eq_id>')
def delete_equivalent(eq_id):
    """删除通用件对"""
    try:
        data = shipping_service.delete_equivalent(eq_id)
    except ShippingRuleChangeConflict as exc:
        return Result.fail('已有发货数据任务正在运行，请等待其结束后重试', data={'task_id': exc.task_id}).to_response(409)
    except ValueError as exc:
        return Result.fail(str(exc)).to_response()
    except Exception:
        return internal_error_response('删除通用件对失败')
    return Result.ok(data).to_response()
