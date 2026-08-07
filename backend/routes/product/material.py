import os
import time
import hashlib

from flask import Blueprint, g, request

from auth import has_permission, make_blueprint_guard
from error_handling import internal_error_response
from result import Result
from routes.product.finished import _decode_image_data_url
from services.product.material import CATEGORY_TYPES, material_service
from services.product.material_combo import material_combo_service
from services.product.material_price import material_price_service
from storage.client import get_bucket
from upload_validation import UploadValidationError
from services.product.material_filter import FilterExpressionError


material_bp = Blueprint('material', __name__)
material_bp.before_request(make_blueprint_guard('product:view', 'product:edit'))
material_cost_bp = Blueprint('material_cost', __name__)
material_cost_bp.before_request(make_blueprint_guard('product:view'))


def _require_rd(permission):
    if not has_permission(g.current_user or {}, permission):
        return Result.fail('无研发成本权限').to_response(403)
    return None


def _material_for_cost(code):
    result = material_service.detail(code)
    return result.data if result.success else None


@material_bp.get('/group-categories')
def group_categories():
    return material_service.group_categories().to_response()


@material_bp.put('/group-categories/<group_code>')
def save_group_category(group_code):
    username = (g.current_user or {}).get('username')
    return material_service.save_group(group_code, request.get_json() or {}, username).to_response()


@material_bp.get('/items')
def list_items():
    try:
        page = max(1, int(request.args.get('page', 1)))
        page_size = min(100, max(1, int(request.args.get('page_size', 20))))
    except ValueError:
        return Result.fail('分页参数无效').to_response()
    category = request.args.get('category', '').strip() or None
    if category and category not in CATEGORY_TYPES:
        return Result.fail('大类参数无效').to_response()
    disabled_arg = request.args.get('is_disabled')
    disabled = None if disabled_arg is None else disabled_arg in ('1', 'true', 'True')
    sort_by = request.args.get('sort_by', 'code').strip() or 'code'
    if sort_by not in ('code', 'name', 'short_name', 'group_code'):
        return Result.fail('排序字段无效').to_response()
    sort_dir = request.args.get('sort_dir', 'asc').strip().lower()
    if sort_dir not in ('asc', 'desc'):
        sort_dir = 'asc'
    match_mode = request.args.get('match_mode', 'like').strip().lower() or 'like'
    if match_mode not in ('like', 'expr'):
        return Result.fail('匹配模式无效').to_response()
    text_filters = {}
    for key in ('code', 'name', 'short_name'):
        raw_value = request.args.get(key)
        if raw_value is None:
            text_filters[key] = None
        elif match_mode == 'expr':
            text_filters[key] = raw_value
        else:
            text_filters[key] = raw_value.strip() or None
    try:
        can_view_cost = has_permission(g.current_user or {}, 'rd:view')
        price_state = request.args.get('price_state', '').strip() or None
        if price_state and not can_view_cost:
            return Result.fail('无研发成本权限').to_response(403)
        if price_state not in (None, 'has', 'none'):
            return Result.fail('价格状态参数无效').to_response()
        result = material_service.list_items(
            page, page_size, category=category,
            group_code=request.args.get('group_code', '').strip() or None,
            keyword=request.args.get('keyword', '').strip() or None,
            **text_filters, sort_by=sort_by, sort_dir=sort_dir, match_mode=match_mode,
            is_disabled=disabled,
            unclassified=request.args.get('unclassified') in ('1', 'true', 'True'),
            price_state=price_state, include_cost=can_view_cost,
        )
    except FilterExpressionError as exc:
        return Result.fail(str(exc)).to_response()
    return result.to_response()


@material_bp.get('/disable-keywords')
def disable_keywords():
    return material_service.disable_keywords().to_response()


@material_bp.post('/disable-keywords')
def create_disable_keyword():
    return material_service.create_disable_keyword(request.get_json() or {}).to_response()


@material_bp.put('/disable-keywords/<int:keyword_id>')
def update_disable_keyword(keyword_id):
    return material_service.update_disable_keyword(
        keyword_id, request.get_json() or {}
    ).to_response()


@material_bp.delete('/disable-keywords/<int:keyword_id>')
def delete_disable_keyword(keyword_id):
    return material_service.delete_disable_keyword(keyword_id).to_response()


@material_bp.get('/disable-preview')
def disable_preview():
    return material_service.disable_preview().to_response()


@material_bp.get('/combos')
def list_material_combos():
    disabled_arg = request.args.get('is_disabled')
    if disabled_arg is None:
        disabled = None
    elif disabled_arg in ('1', 'true', 'True'):
        disabled = True
    elif disabled_arg in ('0', 'false', 'False'):
        disabled = False
    else:
        return Result.fail('停用状态参数无效').to_response()
    return material_combo_service.list(
        keyword=request.args.get('keyword', '').strip() or None,
        category=request.args.get('category', '').strip() or None,
        is_disabled=disabled,
    ).to_response()


@material_bp.get('/combos/categories')
def material_combo_categories():
    return material_combo_service.categories().to_response()


@material_bp.get('/combos/<int:combo_id>')
def material_combo_detail(combo_id):
    result = material_combo_service.get_one(combo_id)
    return result.to_response(200 if result.success else 404)


@material_bp.post('/combos')
def create_material_combo():
    username = (g.current_user or {}).get('username')
    return material_combo_service.save(
        request.get_json(silent=True) or {}, created_by=username,
    ).to_response()


@material_bp.put('/combos/<int:combo_id>')
def update_material_combo(combo_id):
    result = material_combo_service.save(
        request.get_json(silent=True) or {}, combo_id=combo_id,
    )
    return result.to_response(200 if result.success else 400)


@material_bp.delete('/combos/<int:combo_id>')
def delete_material_combo(combo_id):
    result = material_combo_service.delete(combo_id)
    return result.to_response(200 if result.success else 404)


@material_bp.get('/items/<path:code>')
def material_detail(code):
    return material_service.detail(
        code, include_cost=has_permission(g.current_user or {}, 'rd:view')
    ).to_response()


@material_bp.put('/items/<path:code>')
def save_material(code):
    return material_service.save_item(code, request.get_json() or {}).to_response()


@material_bp.post('/items/<path:code>/image')
def upload_material_image(code):
    body = request.get_json() or {}
    try:
        image_bytes, ext = _decode_image_data_url((body.get('data_url') or '').strip(), '物料图片')
        original = (
            _decode_image_data_url((body.get('orig_data_url') or '').strip(), '原始物料图片')
            if body.get('orig_data_url') else None
        )
    except UploadValidationError as exc:
        return Result.fail(str(exc)).to_response(413 if '不能超过' in str(exc) else 400)
    if not material_service.detail(code).success:
        return Result.fail('物料不存在').to_response(404)
    try:
        bucket = get_bucket()
        base_url = os.getenv('OSS_BASE_URL', '').rstrip('/')
        safe_code = hashlib.sha256(code.encode('utf-8')).hexdigest()
        rel_path = f'materials/{safe_code}.{ext}'
        bucket.put_object(f'tmt-library/{rel_path}', image_bytes)
        url = f'{base_url}/{rel_path}'
        orig_url = None
        if original:
            orig_bytes, orig_ext = original
            orig_path = f'materials/{safe_code}_orig.{orig_ext}'
            bucket.put_object(f'tmt-library/{orig_path}', orig_bytes)
            orig_url = f'{base_url}/{orig_path}'
        timestamp = int(time.time())
        payload = {'cover_image': url, 'img_updated_at': timestamp}
        if orig_url:
            payload['cover_image_original'] = orig_url
        material_service.save_item(code, payload)
        return Result.ok(data={
            'url': url, 'orig_url': orig_url, 'img_updated_at': timestamp,
            'cover_image': url, 'cover_image_original': orig_url,
        }).to_response()
    except Exception:
        return internal_error_response('物料图片上传失败', '上传失败')


@material_cost_bp.get('/items/<path:code>/prices')
def material_prices(code):
    denied = _require_rd('rd:view')
    if denied:
        return denied
    material = _material_for_cost(code)
    if not material:
        return Result.fail('物料不存在').to_response(404)
    return material_price_service.list_prices(material).to_response()


@material_cost_bp.post('/items/<path:code>/prices')
def add_material_price(code):
    denied = _require_rd('rd:edit')
    if denied:
        return denied
    material = _material_for_cost(code)
    if not material:
        return Result.fail('物料不存在').to_response(404)
    return material_price_service.add_price(
        material, request.get_json(silent=True) or {},
        (g.current_user or {}).get('username'),
    ).to_response()


@material_cost_bp.patch('/prices/<int:price_id>')
def update_material_price(price_id):
    denied = _require_rd('rd:edit')
    if denied:
        return denied
    return material_price_service.update_price(
        price_id, request.get_json(silent=True) or {},
    ).to_response()


@material_cost_bp.delete('/prices/<int:price_id>')
def delete_material_price(price_id):
    denied = _require_rd('rd:edit')
    if denied:
        return denied
    return material_price_service.delete_price(price_id).to_response()


@material_cost_bp.get('/items/<path:code>/usages')
def material_usages(code):
    denied = _require_rd('rd:view')
    if denied:
        return denied
    material = _material_for_cost(code)
    if not material:
        return Result.fail('物料不存在').to_response(404)
    return material_price_service.usages(material).to_response()
