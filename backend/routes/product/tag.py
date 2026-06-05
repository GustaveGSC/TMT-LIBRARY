from flask import Blueprint, request, g
from services.product.tag import TagService, TagCategoryService
from auth import make_blueprint_guard

bp = Blueprint('tag', __name__)
bp.before_request(make_blueprint_guard('product:view', 'product:edit'))


# ── 标签分类 CRUD ─────────────────────────────────────────────────────────

@bp.get('/categories/')
def list_categories():
    return TagCategoryService.get_all().to_response()


@bp.post('/categories/')
def create_category():
    body       = request.get_json() or {}
    name       = body.get('name', '')
    color      = body.get('color', '#c4883a')
    sort_order = body.get('sort_order', 0)
    return TagCategoryService.create(name=name, color=color, sort_order=sort_order).to_response()


@bp.put('/categories/<int:category_id>')
def update_category(category_id):
    body       = request.get_json() or {}
    name       = body.get('name', '')
    color      = body.get('color', '#c4883a')
    sort_order = body.get('sort_order', 0)
    return TagCategoryService.update(category_id=category_id, name=name, color=color, sort_order=sort_order).to_response()


@bp.delete('/categories/<int:category_id>')
def delete_category(category_id):
    return TagCategoryService.delete(category_id=category_id).to_response()


# ── 标签 CRUD ─────────────────────────────────────────────────────────────

@bp.get('/')
def list_tags():
    return TagService.get_all().to_response()


@bp.post('/')
def create_tag():
    body        = request.get_json() or {}
    name        = body.get('name', '')
    category_id = body.get('category_id')
    color       = body.get('color')   # 兼容旧调用
    return TagService.create(name=name, category_id=category_id, color=color).to_response()


@bp.put('/<int:tag_id>')
def update_tag(tag_id):
    body        = request.get_json() or {}
    name        = body.get('name', '')
    category_id = body.get('category_id')
    color       = body.get('color')
    return TagService.update(tag_id=tag_id, name=name, category_id=category_id, color=color).to_response()


@bp.delete('/<int:tag_id>')
def delete_tag(tag_id):
    return TagService.delete(tag_id=tag_id).to_response()


# ── 成品关联 ──────────────────────────────────────────────────────────────

@bp.post('/finished/<int:finished_id>/<int:tag_id>')
def add_to_finished(finished_id, tag_id):
    return TagService.add_to_finished(finished_id=finished_id, tag_id=tag_id).to_response()


@bp.delete('/finished/<int:finished_id>/<int:tag_id>')
def remove_from_finished(finished_id, tag_id):
    return TagService.remove_from_finished(finished_id=finished_id, tag_id=tag_id).to_response()
