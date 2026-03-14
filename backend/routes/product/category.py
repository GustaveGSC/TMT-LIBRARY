from flask import Blueprint, request
from services.product.category import category_service
from result import Result

category_bp = Blueprint('category', __name__)


# ── 完整树 ────────────────────────────────────────────────────────────────
@category_bp.get('/tree')
def get_tree():
    return category_service.get_tree().to_response()


# ── Category CRUD ─────────────────────────────────────────────────────────
@category_bp.post('/categories')
def create_category():
    body       = request.get_json() or {}
    name       = (body.get('name') or '').strip()
    sort_order = int(body.get('sort_order', 0))
    if not name:
        return Result.fail('name 不能为空').to_response()
    return category_service.create_category(name, sort_order).to_response()

@category_bp.put('/categories/<int:category_id>')
def update_category(category_id: int):
    body = request.get_json() or {}
    return category_service.update_category(category_id, **body).to_response()

@category_bp.delete('/categories/<int:category_id>')
def delete_category(category_id: int):
    return category_service.delete_category(category_id).to_response()


# ── Series CRUD ───────────────────────────────────────────────────────────
@category_bp.post('/series')
def create_series():
    body        = request.get_json() or {}
    category_id = body.get('category_id')
    code        = (body.get('code') or '').strip()
    name        = (body.get('name') or '').strip()
    sort_order  = int(body.get('sort_order', 0))
    if not category_id or not code or not name:
        return Result.fail('category_id、code 和 name 不能为空').to_response()
    return category_service.create_series(int(category_id), code, name, sort_order).to_response()

@category_bp.put('/series/<int:series_id>')
def update_series(series_id: int):
    body = request.get_json() or {}
    return category_service.update_series(series_id, **body).to_response()

@category_bp.delete('/series/<int:series_id>')
def delete_series(series_id: int):
    return category_service.delete_series(series_id).to_response()


# ── Model CRUD ────────────────────────────────────────────────────────────
@category_bp.post('/models')
def create_model():
    body       = request.get_json() or {}
    series_id  = body.get('series_id')
    code       = (body.get('code')       or '').strip()
    name       = (body.get('name')       or '').strip()
    model_code = (body.get('model_code') or '').strip()
    name_en    = (body.get('name_en')    or '').strip()
    sort_order = int(body.get('sort_order', 0))
    if not series_id or not code or not name or not model_code:
        return Result.fail('series_id、code、name、model_code 不能为空').to_response()
    return category_service.create_model(
        int(series_id), code, name,
        model_code=model_code, name_en=name_en, sort_order=sort_order
    ).to_response()

@category_bp.put('/models/<int:model_id>')
def update_model(model_id: int):
    body = request.get_json() or {}
    return category_service.update_model(model_id, **body).to_response()

@category_bp.delete('/models/<int:model_id>')
def delete_model(model_id: int):
    return category_service.delete_model(model_id).to_response()