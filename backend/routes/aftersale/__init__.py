import uuid
import time
import threading
import urllib.parse
from flask import Blueprint, request, Response, current_app, g
from services.aftersale import AftersaleService
from auth import make_blueprint_guard
from result import Result

# 异步导出任务：task_id → {'status': 'pending'|'done'|'error', 'data': bytes, 'message': str, '_at': float}
_export_tasks: dict = {}
_EXPORT_TTL = 1800  # 30 分钟后自动清理


def _cleanup_export_tasks():
    """清理超过 TTL 的任务（在每次新建任务时调用）"""
    cutoff = time.time() - _EXPORT_TTL
    stale = [k for k, v in _export_tasks.items() if v.get('_at', 0) < cutoff]
    for k in stale:
        _export_tasks.pop(k, None)

aftersale_bp = Blueprint('aftersale', __name__)
_svc = AftersaleService()

aftersale_bp.before_request(make_blueprint_guard('aftersale:view', 'aftersale:edit', 'aftersale:export'))



# ── 发货物料简称库 ─────────────────────────────────────────────────────────

@aftersale_bp.get('/shipping-aliases')
def get_shipping_aliases():
    return _svc.get_shipping_aliases().to_response()


@aftersale_bp.post('/shipping-aliases')
def create_shipping_alias():
    return _svc.create_shipping_alias(request.get_json() or {}).to_response()


@aftersale_bp.put('/shipping-aliases/<int:alias_id>')
def update_shipping_alias(alias_id):
    return _svc.update_shipping_alias(alias_id, request.get_json() or {}).to_response()


@aftersale_bp.delete('/shipping-aliases/<int:alias_id>')
def delete_shipping_alias(alias_id):
    return _svc.delete_shipping_alias(alias_id).to_response()


@aftersale_bp.post('/shipping-aliases/<int:source_id>/merge-into/<int:target_id>')
def merge_shipping_alias(source_id, target_id):
    return _svc.merge_shipping_alias(source_id, target_id).to_response()


# ── 一级分类 ───────────────────────────────────────────────────────────────

@aftersale_bp.get('/reason-categories')
def get_reason_categories():
    return _svc.get_categories().to_response()


@aftersale_bp.post('/reason-categories')
def create_reason_category():
    return _svc.create_category(request.get_json() or {}).to_response()


@aftersale_bp.put('/reason-categories/<int:cat_id>')
def update_reason_category(cat_id):
    return _svc.update_category(cat_id, request.get_json() or {}).to_response()


@aftersale_bp.delete('/reason-categories/<int:cat_id>')
def delete_reason_category(cat_id):
    return _svc.delete_category(cat_id).to_response()


# ── 二级原因 ───────────────────────────────────────────────────────────────

@aftersale_bp.get('/reasons')
def get_reasons():
    return _svc.get_reasons().to_response()


@aftersale_bp.post('/reasons')
def create_reason():
    return _svc.create_reason(request.get_json() or {}).to_response()


@aftersale_bp.put('/reasons/<int:reason_id>')
def update_reason(reason_id):
    return _svc.update_reason(reason_id, request.get_json() or {}).to_response()


@aftersale_bp.delete('/reasons/<int:reason_id>')
def delete_reason(reason_id):
    return _svc.delete_reason(reason_id).to_response()


@aftersale_bp.get('/reasons/<int:reason_id>/usage')
def get_reason_usage(reason_id):
    return _svc.get_reason_usage(reason_id).to_response()


@aftersale_bp.get('/case-edit-options')
def get_case_edit_options():
    return _svc.get_case_edit_options().to_response()


@aftersale_bp.patch('/case-reasons/<int:cr_id>')
def update_case_reason(cr_id):
    return _svc.update_case_reason(cr_id, request.get_json() or {}).to_response()


@aftersale_bp.post('/reasons/<int:source_id>/merge-into/<int:target_id>')
def merge_reason(source_id, target_id):
    return _svc.merge_reason(source_id, target_id).to_response()


# ── 产品型号推断 ──────────────────────────────────────────────────────────────

@aftersale_bp.post('/suggest-product')
def suggest_product():
    body = request.get_json() or {}
    return _svc.suggest_product(body, semantic=body.get('semantic', True)).to_response()


# ── 待处理订单 ──────────────────────────────────────────────────────────────

@aftersale_bp.get('/pending')
def get_pending():
    page       = int(request.args.get('page', 1))
    page_size  = int(request.args.get('page_size', 50))
    search     = request.args.get('search')
    date_start = request.args.get('date_start')
    date_end   = request.args.get('date_end')
    return _svc.get_pending_orders(page, page_size, search, date_start, date_end).to_response()


@aftersale_bp.get('/pending/count')
def get_pending_count():
    return _svc.get_pending_count().to_response()


# ── 工单 ────────────────────────────────────────────────────────────────────

@aftersale_bp.get('/cases')
def get_cases():
    def _ints(key):
        raw = request.args.get(key, '')
        return [int(x) for x in raw.split(',') if x.strip().lstrip('-').isdigit()]
    def _strs(key):
        raw = request.args.get(key, '')
        return [x for x in raw.split(',') if x.strip()]

    page       = int(request.args.get('page', 1))
    page_size  = int(request.args.get('page_size', 50))
    status     = request.args.get('status')
    date_start = request.args.get('date_start')
    date_end   = request.args.get('date_end')
    reason_id  = request.args.get('reason_id', type=int)
    channel    = request.args.get('channel_name')
    province   = request.args.get('province')
    search          = request.args.get('search')
    city            = request.args.get('city')
    district        = request.args.get('district')
    reason_category = request.args.get('reason_category')
    reason_name     = request.args.get('reason_name')
    shipping_alias  = request.args.get('shipping_alias')
    model_code      = request.args.get('model_code')
    sort_by         = request.args.get('sort_by')
    sort_order      = request.args.get('sort_order', 'desc')
    max_days        = request.args.get('max_days_since_purchase', type=int)
    return _svc.get_cases(
        page, page_size, status, date_start, date_end,
        reason_id, channel, province, city, district,
        reason_category, reason_name, shipping_alias,
        model_code, search, sort_by=sort_by, sort_order=sort_order,
        max_days_since_purchase=max_days,
        model_ids=_ints('model_ids'),
        series_ids=_ints('series_ids'),
        category_ids=_ints('category_ids'),
        reason_ids=_ints('reason_ids'),
        reason_category_ids=_ints('reason_category_ids'),
        shipping_alias_ids=_ints('shipping_alias_ids'),
        channel_names=_strs('channel_names'),
        provinces=_strs('provinces'),
        cities=_strs('cities'),
    ).to_response()


@aftersale_bp.post('/cases/export/start')
def export_cases_start():
    """启动后台导出线程，立即返回 task_id；前端轮询 status 后再下载"""
    body = request.get_json() or {}

    def _extract(key, cast=None, default=None):
        v = body.get(key, default)
        if v is None:
            return default
        return cast(v) if cast else v

    _cleanup_export_tasks()
    task_id = str(uuid.uuid4())
    _export_tasks[task_id] = {'status': 'pending', '_at': time.time()}
    app = current_app._get_current_object()

    kwargs = dict(
        status         = _extract('status') or 'confirmed',
        date_start     = _extract('date_start'),
        date_end       = _extract('date_end'),
        reason_id      = _extract('reason_id', int),
        channel_name   = _extract('channel_name'),
        province       = _extract('province'),
        city           = _extract('city'),
        district       = _extract('district'),
        reason_category= _extract('reason_category'),
        reason_name    = _extract('reason_name'),
        shipping_alias = _extract('shipping_alias'),
        model_code     = _extract('model_code'),
        search         = _extract('search'),
        sort_by        = _extract('sort_by'),
        sort_order     = _extract('sort_order') or 'desc',
    )

    def run():
        with app.app_context():
            try:
                xlsx_bytes = _svc.export_cases(**kwargs)
                _export_tasks[task_id] = {'status': 'done', 'data': xlsx_bytes, '_at': time.time()}
            except Exception as e:
                _export_tasks[task_id] = {'status': 'error', 'message': str(e), '_at': time.time()}

    threading.Thread(target=run, daemon=True).start()
    return Result.ok(data={'task_id': task_id}).to_response()


@aftersale_bp.get('/cases/export/status/<task_id>')
def export_cases_status(task_id):
    """轮询导出进度"""
    task = _export_tasks.get(task_id)
    if not task:
        return Result.fail('任务不存在').to_response()
    if task['status'] == 'error':
        _export_tasks.pop(task_id, None)
    return Result.ok(data={'status': task['status'], 'message': task.get('message', '')}).to_response()


@aftersale_bp.get('/cases/export/download/<task_id>')
def export_cases_download(task_id):
    """下载已生成的 xlsx，下载后自动清理任务"""
    task = _export_tasks.pop(task_id, None)
    if not task or task['status'] != 'done':
        return Result.fail('导出任务未完成或不存在').to_response()

    from datetime import date as _date
    filename = f'售后数据_{_date.today().strftime("%Y%m%d")}.xlsx'
    encoded  = urllib.parse.quote(filename)
    return Response(
        task['data'],
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{encoded}",
            'Content-Length': str(len(task['data'])),
        },
    )


@aftersale_bp.get('/cases/reasons')
def get_cases_reasons():
    ids_str = request.args.get('ids', '')
    try:
        case_ids = [int(i) for i in ids_str.split(',') if i.strip()]
    except ValueError:
        case_ids = []
    return _svc.get_cases_reasons(case_ids).to_response()


@aftersale_bp.get('/filter-options')
def get_filter_options():
    return _svc.get_filter_options().to_response()


@aftersale_bp.get('/cases/<int:case_id>')
def get_case(case_id):
    return _svc.get_case(case_id).to_response()


@aftersale_bp.post('/cases')
def confirm_case():
    return _svc.confirm_case(request.get_json() or {}).to_response()


@aftersale_bp.put('/cases/<int:case_id>')
def update_case(case_id):
    return _svc.update_case(case_id, request.get_json() or {}).to_response()


@aftersale_bp.post('/cases/<string:order_no>/ignore')
def ignore_case(order_no):
    return _svc.ignore_case(order_no).to_response()


# ── 发货物料匹配过滤词 ───────────────────────────────────────────────────────

@aftersale_bp.get('/shipping-ignore-terms')
def get_ignore_terms():
    return _svc.get_ignore_terms().to_response()


@aftersale_bp.post('/shipping-ignore-terms')
def create_ignore_term():
    return _svc.create_ignore_term(request.get_json() or {}).to_response()


@aftersale_bp.delete('/shipping-ignore-terms/<int:term_id>')
def delete_ignore_term(term_id):
    return _svc.delete_ignore_term(term_id).to_response()


# ── 发货物料歧义词 ──────────────────────────────────────────────────────────

@aftersale_bp.get('/shipping-ambiguous-terms')
def get_ambiguous_terms():
    return _svc.get_ambiguous_terms().to_response()


@aftersale_bp.post('/shipping-ambiguous-terms')
def create_ambiguous_term():
    return _svc.create_ambiguous_term(request.get_json() or {}).to_response()


@aftersale_bp.delete('/shipping-ambiguous-terms/<int:term_id>')
def delete_ambiguous_term(term_id):
    return _svc.delete_ambiguous_term(term_id).to_response()


# ── 售后原因关键词词典（标准档）──────────────────────────────────────────────

@aftersale_bp.get('/reason-keyword-rules')
def get_reason_keyword_rules():
    return _svc.get_reason_keyword_rules().to_response()


@aftersale_bp.put('/reason-keyword-rules')
def update_reason_keyword_rules():
    return _svc.update_reason_keyword_rules(request.get_json() or {}).to_response()


# ── 产品留言词典（材质/颜色/驱动/尺寸）──────────────────────────────────────

@aftersale_bp.get('/product-remark-dict')
def get_product_remark_dict():
    return _svc.get_product_remark_dict().to_response()


@aftersale_bp.put('/product-remark-dict')
def put_product_remark_dict():
    body = request.get_json() or {}
    items = body.get('items', [])
    return _svc.put_product_remark_dict(items).to_response()


# ── 自动匹配 ────────────────────────────────────────────────────────────────

@aftersale_bp.post('/auto-match')
def auto_match():
    body = request.get_json() or {}
    semantic = body.get('semantic', True)
    model_id = body.get('model_id') or None
    return _svc.auto_match(body.get('text', ''), body.get('buyer_remark', ''), semantic=semantic, model_id=model_id).to_response()


# ── 统计 & 图表 ─────────────────────────────────────────────────────────────

@aftersale_bp.get('/stats')
def get_stats():
    return _svc.get_stats().to_response()


@aftersale_bp.get('/chart-options')
def get_chart_options():
    return _svc.get_chart_options().to_response()


@aftersale_bp.post('/chart-filter-options')
def get_cross_filter_options():
    return _svc.get_cross_filter_options(request.get_json() or {}).to_response()


@aftersale_bp.post('/chart-data')
def get_chart_data():
    return _svc.get_chart_data(request.get_json() or {}).to_response()


# ── 词典自动建议 ──────────────────────────────────────────────────────────────

@aftersale_bp.get('/dictionary-suggestions')
def get_dict_suggestions():
    type_filter = request.args.get('type')
    status = request.args.get('status', 'pending')
    return _svc.get_dict_suggestions(type_filter=type_filter, status=status).to_response()


@aftersale_bp.post('/dictionary-suggestions/<int:sug_id>/accept')
def accept_dict_suggestion(sug_id):
    return _svc.accept_dict_suggestion(sug_id).to_response()


@aftersale_bp.post('/dictionary-suggestions/<int:sug_id>/reject')
def reject_dict_suggestion(sug_id):
    return _svc.reject_dict_suggestion(sug_id).to_response()


# ── 原因-简称亲和度 ───────────────────────────────────────────────────────────

@aftersale_bp.post('/alias-affinity')
def get_alias_affinity():
    body      = request.get_json() or {}
    reason_id = body.get('reason_id')
    alias_ids = body.get('alias_ids', [])
    if not reason_id or not alias_ids:
        return _svc.get_alias_affinity(None, []).to_response()
    return _svc.get_alias_affinity(int(reason_id), [int(i) for i in alias_ids]).to_response()


# ── 管理工具 ─────────────────────────────────────────────────────────────────

@aftersale_bp.post('/admin/migrate-alias-keywords')
def migrate_alias_keywords():
    return _svc.migrate_alias_keywords().to_response()


@aftersale_bp.get('/admin/keyword-candidate-stats')
def keyword_candidate_stats():
    return _svc.get_keyword_candidate_stats().to_response()


@aftersale_bp.post('/admin/cleanup-keyword-candidates')
def cleanup_keyword_candidates():
    body          = request.get_json() or {}
    min_count     = int(body.get('min_count', 2))
    top_per_reason = int(body.get('top_per_reason', 200))
    return _svc.cleanup_keyword_candidates(min_count=min_count, top_per_reason=top_per_reason).to_response()


# ── 产品库展开行：系列售后月度数据 ────────────────────────────────────────────

@aftersale_bp.get('/model/<int:model_id>/series-monthly')
def get_series_monthly(model_id):
    """按月聚合指定 model 所属系列的售后工单数 + 发货实际量（仅有售后数据的月份）"""
    return _svc.get_series_monthly_by_model_id(model_id).to_response()


# ── 通用设置 ─────────────────────────────────────────────────────────────────

@aftersale_bp.get('/settings')
def get_settings():
    return _svc.get_settings().to_response()


@aftersale_bp.put('/settings')
def update_setting():
    return _svc.update_setting(request.get_json() or {}).to_response()


# ── 语义向量模型管理 ──────────────────────────────────────────────────────────

@aftersale_bp.get('/model/status')
def model_status():
    import model_manager
    from result import Result
    installed = model_manager.is_model_installed()
    ready     = model_manager.get_model() is not None
    return Result.ok(data={
        'installed': installed,
        'ready':     ready,
    }).to_response()


@aftersale_bp.post('/model/download')
def model_download():
    import model_manager
    from result import Result
    if model_manager.is_model_installed():
        return Result.ok(message='模型已安装').to_response()
    started = model_manager.start_download()
    return Result.ok(data={'started': started}).to_response()


@aftersale_bp.get('/model/progress')
def model_progress():
    import model_manager
    from result import Result
    return Result.ok(data=model_manager.get_download_state()).to_response()
