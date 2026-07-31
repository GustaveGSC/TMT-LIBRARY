import os
import time

from flask import Blueprint, g, request

from auth import make_blueprint_guard
from error_handling import internal_error_response
from result import Result
from routes.product.finished import _decode_image_data_url
from services.product.material import CATEGORY_TYPES, material_service
from storage.client import get_bucket
from upload_validation import UploadValidationError


material_bp = Blueprint('material', __name__)
material_bp.before_request(make_blueprint_guard('product:view', 'product:edit'))


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
    return material_service.list_items(
        page, page_size, category=category,
        group_code=request.args.get('group_code', '').strip() or None,
        keyword=request.args.get('keyword', '').strip() or None,
        is_disabled=disabled,
        unclassified=request.args.get('unclassified') in ('1', 'true', 'True'),
    ).to_response()


@material_bp.get('/items/<code>')
def material_detail(code):
    return material_service.detail(code).to_response()


@material_bp.put('/items/<code>')
def save_material(code):
    return material_service.save_item(code, request.get_json() or {}).to_response()


@material_bp.post('/items/<code>/image')
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
        rel_path = f'materials/{code}.{ext}'
        bucket.put_object(f'tmt-library/{rel_path}', image_bytes)
        url = f'{base_url}/{rel_path}'
        orig_url = None
        if original:
            orig_bytes, orig_ext = original
            orig_path = f'materials/{code}_orig.{orig_ext}'
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
