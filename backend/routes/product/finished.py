import base64
import os
import re
import time

from flask import Blueprint, request, g
from services.product.finished import finished_service
from database.repository.product.category import CategoryRepository
from storage.client import get_bucket
from auth import make_blueprint_guard
from result import Result

finished_bp = Blueprint('finished', __name__)
finished_bp.before_request(make_blueprint_guard('product:view', 'product:edit'))


# ── 成品列表 ──────────────────────────────────────────────────────────────
@finished_bp.get('/finished')
def list_finished():
    page         = int(request.args.get('page',         1))
    size         = int(request.args.get('size',         20))
    search_field = request.args.get('search_field', '').strip()
    search_value = request.args.get('search_value', '').strip()
    status       = request.args.get('status',       '').strip()
    return finished_service.get_finished_list(
        page, size, search_field, search_value, status
    ).to_response()


# ── 保存成品信息（新增或更新）────────────────────────────────────────────
@finished_bp.post('/finished')
def save_finished():
    body = request.get_json() or {}
    code = (body.pop('code', '') or '').strip()
    if not code:
        return Result.fail('code 不能为空').to_response()

    # 提取分类相关字段（不传入 service）
    category_name = (body.pop('category_name', '') or '').strip()
    series_code   = (body.pop('series_code',   '') or '').strip()
    series_name   = (body.pop('series_name',   '') or '').strip()
    model_code    = (body.pop('model_code',    '') or '').strip()
    name_en       = (body.pop('name_en',       '') or '').strip()
    name_zh = (body.pop('name', '') or '').strip()   # 用于更新 product_model.name

    # ── get-or-create: category → series → model ──
    if model_code and category_name and series_code:
        # 品类
        category = CategoryRepository.get_category_by_name(category_name)
        if not category:
            category = CategoryRepository.create_category(category_name)

        # 系列（按 code 查找，name 用于新建）
        series = CategoryRepository.get_series_by_code(category.id, series_code)
        if not series:
            series = CategoryRepository.create_series(
                category.id, series_code, series_name or series_code
            )

        # 型号（按 model_code 查找）
        model = CategoryRepository.get_model_by_model_code(model_code)
        if not model:
            model = CategoryRepository.create_model(
                series_id=series.id,
                code=code,                  # finished product code
                name=name_zh or code,       # 中文名（表单输入），fallback 到成品编码
                model_code=model_code,
                name_en=name_en or None,
            )
        else:
            # 型号已存在 → 按需更新英文名 / 中文名
            updates = {}
            if name_en and model.name_en != name_en:
                updates['name_en'] = name_en
            if name_zh and model.name != name_zh:
                updates['name'] = name_zh
            if updates:
                CategoryRepository.update_model(model, **updates)

        body['model_id'] = model.id

    elif model_code:
        # 仅有 model_code 无分类信息时，按原有逻辑查找
        model = CategoryRepository.get_model_by_model_code(model_code)
        if model:
            updates = {}
            if name_en and model.name_en != name_en:
                updates['name_en'] = name_en
            if name_zh and model.name != name_zh:
                updates['name'] = name_zh
            if updates:
                CategoryRepository.update_model(model, **updates)
            body['model_id'] = model.id
        else:
            body['model_id'] = None

    # model_id 成功解析时，若状态仍为未录入则自动升级为已录入
    if body.get('model_id') and body.get('status') == 'unrecorded':
        body['status'] = 'recorded'

    return finished_service.save_finished(code, **body).to_response()


# ── 产成品候选（不分页，用于下拉选项）───────────────────────────────────
@finished_bp.get('/packaged/candidates/all')
def list_packaged_candidates_all():
    return finished_service.get_all_packaged_candidate_codes().to_response()


# ── 全量产成品（供前端预加载）────────────────────────────────────────────
@finished_bp.get('/packaged/all')
def list_packaged_all():
    return finished_service.get_all_packaged().to_response()


# ── 产成品候选列表 ────────────────────────────────────────────────────────
@finished_bp.get('/packaged/candidates')
def list_packaged_candidates():
    search = request.args.get('search', '').strip()
    page   = int(request.args.get('page', 1))
    size   = int(request.args.get('size', 20))
    return finished_service.get_packaged_candidates(search, page, size).to_response()


# ── 保存产成品信息 ────────────────────────────────────────────────────────
@finished_bp.post('/packaged')
def save_packaged():
    body = request.get_json() or {}
    code = (body.pop('code', '') or '').strip()
    name = (body.pop('name', '') or '').strip()
    if not code or not name:
        return Result.fail('code 和 name 不能为空').to_response()
    return finished_service.save_packaged(code, name, **body).to_response()


# ── 某成品关联的产成品列表 ────────────────────────────────────────────────
@finished_bp.get('/finished/<int:finished_id>/packaged')
def get_packaged_by_finished(finished_id: int):
    return finished_service.get_packaged_by_finished(finished_id).to_response()


# ── 添加关联 ──────────────────────────────────────────────────────────────
@finished_bp.post('/finished/<int:finished_id>/packaged/<int:packaged_id>')
def add_packaged_relation(finished_id: int, packaged_id: int):
    return finished_service.add_packaged_relation(finished_id, packaged_id).to_response()


# ── 移除关联 ──────────────────────────────────────────────────────────────
@finished_bp.delete('/finished/<int:finished_id>/packaged/<int:packaged_id>')
def remove_packaged_relation(finished_id: int, packaged_id: int):
    return finished_service.remove_packaged_relation(finished_id, packaged_id).to_response()


# ── 上传封面图到 OSS ──────────────────────────────────────────────────────
@finished_bp.post('/finished/cover-image')
def upload_cover_image():
    body          = request.get_json() or {}
    code          = (body.get('code')          or '').strip()
    data_url      = (body.get('data_url')      or '').strip()
    orig_data_url = (body.get('orig_data_url') or '').strip()   # 可选：原始高清图
    if not code or not data_url:
        return Result.fail('参数缺失').to_response()

    match = re.match(r'data:image/(\w+);base64,(.+)', data_url, re.DOTALL)
    if not match:
        return Result.fail('无效的图片数据').to_response()

    ext       = match.group(1)          # png
    img_bytes = base64.b64decode(match.group(2))
    rel_path  = f'products/{code}.{ext}'          # 相对于 tmt-library/ 的路径
    key       = f'tmt-library/{rel_path}'         # bucket 内完整 key

    try:
        bucket   = get_bucket()
        base_url = os.getenv('OSS_BASE_URL', '').rstrip('/')   # 已含 /tmt-library
        bucket.put_object(key, img_bytes)
        url = f'{base_url}/{rel_path}'

        # 同步上传原始高清图（可选）
        orig_url = None
        if orig_data_url:
            orig_match = re.match(r'data:image/(\w+);base64,(.+)', orig_data_url, re.DOTALL)
            if orig_match:
                orig_ext   = orig_match.group(1)
                orig_bytes = base64.b64decode(orig_match.group(2))
                orig_key   = f'tmt-library/products/{code}_orig.{orig_ext}'
                bucket.put_object(orig_key, orig_bytes)
                orig_url = f'{base_url}/products/{code}_orig.{orig_ext}'

        # 更新 img_updated_at，用于前端缓存破坏
        ts = int(time.time())
        save_kwargs = dict(cover_image=url, img_updated_at=ts)
        if orig_url is not None:
            save_kwargs['cover_image_original'] = orig_url
        finished_service.save_finished(code, **save_kwargs)
        return Result.ok(data={'url': url, 'orig_url': orig_url, 'img_updated_at': ts}).to_response()
    except Exception as e:
        return Result.fail(f'上传失败：{str(e)}').to_response()


@finished_bp.post('/finished/copy-cover-image')
def copy_cover_image():
    """把 from_code 的封面图复制一份到 to_code，两者图片文件独立互不影响。"""
    body      = request.get_json() or {}
    from_code = (body.get('from_code') or '').strip()
    to_code   = (body.get('to_code')   or '').strip()
    if not from_code or not to_code:
        return Result.fail('参数缺失').to_response()
    if from_code == to_code:
        return Result.fail('来源与目标相同').to_response()

    try:
        bucket   = get_bucket()
        base_url = os.getenv('OSS_BASE_URL', '').rstrip('/')
        src_key  = f'tmt-library/products/{from_code}.png'
        dst_key  = f'tmt-library/products/{to_code}.png'
        bucket.copy_object(bucket.bucket_name, src_key, dst_key)
        url = f'{base_url}/products/{to_code}.png'

        # 若来源有原始高清图，一并复制
        orig_url = None
        src_orig_key = f'tmt-library/products/{from_code}_orig.png'
        try:
            bucket.get_object_meta(src_orig_key)   # 检查是否存在（不存在会抛异常）
            dst_orig_key = f'tmt-library/products/{to_code}_orig.png'
            bucket.copy_object(bucket.bucket_name, src_orig_key, dst_orig_key)
            orig_url = f'{base_url}/products/{to_code}_orig.png'
        except Exception:
            pass   # 来源无原始图，跳过

        ts = int(time.time())
        save_kwargs = dict(cover_image=url, img_updated_at=ts)
        if orig_url:
            save_kwargs['cover_image_original'] = orig_url
        finished_service.save_finished(to_code, **save_kwargs)
        return Result.ok(data={'url': url, 'orig_url': orig_url, 'img_updated_at': ts}).to_response()
    except Exception as e:
        return Result.fail(f'复制失败：{str(e)}').to_response()