from flask import Blueprint, request
from services.aftersale import AftersaleService

aftersale_bp = Blueprint('aftersale', __name__)
_svc = AftersaleService()



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


# ── 产品型号推断 ──────────────────────────────────────────────────────────────

@aftersale_bp.post('/suggest-product')
def suggest_product():
    return _svc.suggest_product(request.get_json() or {}).to_response()


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
    return _svc.get_cases(
        page, page_size, status, date_start, date_end,
        reason_id, channel, province, city, district,
        reason_category, reason_name, shipping_alias,
        model_code, search, sort_by=sort_by, sort_order=sort_order,
    ).to_response()


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


# ── 售后原因关键词词典（标准档）──────────────────────────────────────────────

@aftersale_bp.get('/reason-keyword-rules')
def get_reason_keyword_rules():
    return _svc.get_reason_keyword_rules().to_response()


@aftersale_bp.put('/reason-keyword-rules')
def update_reason_keyword_rules():
    return _svc.update_reason_keyword_rules(request.get_json() or {}).to_response()


# ── 自动匹配 ────────────────────────────────────────────────────────────────

@aftersale_bp.post('/auto-match')
def auto_match():
    body = request.get_json() or {}
    return _svc.auto_match(body.get('text', ''), body.get('buyer_remark', '')).to_response()


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
    body = request.get_json() or {}
    return _svc.accept_dict_suggestion(
        sug_id,
        target_type=body.get('target_type'),
        canonical=body.get('canonical'),
    ).to_response()


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
