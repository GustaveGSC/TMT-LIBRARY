import os
import uuid
import time
from datetime import datetime

from flask import Blueprint, request, g
from services.product.resource import resource_service
from storage.client import get_bucket
from auth import make_blueprint_guard
from result import Result

resource_bp = Blueprint('resource', __name__)
resource_bp.before_request(make_blueprint_guard('product:view', 'product:edit'))

OSS_BASE_URL = os.getenv('OSS_BASE_URL', '').rstrip('/')

VALID_FILE_TYPES = {'pdf', 'image', 'video', 'link', 'other'}
UPLOAD_EXT_MAP = {
    'pdf':  ('application/pdf',  'pdf'),
    'png':  ('image/png',        'image'),
    'jpg':  ('image/jpeg',       'image'),
    'jpeg': ('image/jpeg',       'image'),
    'webp': ('image/webp',       'image'),
}
PREVIEW_CONTENT_TYPES = {
    'pdf':  'application/pdf',
    'png':  'image/png',
    'jpg':  'image/jpeg',
    'jpeg': 'image/jpeg',
    'webp': 'image/webp',
}


def _preview_content_type(resource: dict) -> str | None:
    if resource.get('file_type') == 'pdf':
        return PREVIEW_CONTENT_TYPES['pdf']
    if resource.get('file_type') != 'image':
        return None
    filename = resource.get('original_filename') or resource.get('storage_key') or resource.get('url') or ''
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return PREVIEW_CONTENT_TYPES.get(ext)


def _require_admin():
    """在路由内检查 admin 角色，非 admin 返回 403 Response，admin 返回 None。"""
    user = getattr(g, 'current_user', {})
    if 'admin' not in user.get('roles', []):
        return Result.fail('仅管理员可操作').to_response(403)
    return None


# ── 资料类型 ──────────────────────────────────────────────────────────────

@resource_bp.get('/types')
def list_types():
    return resource_service.list_types().to_response()


@resource_bp.post('/types')
def create_type():
    err = _require_admin()
    if err: return err
    body       = request.get_json() or {}
    name       = (body.get('name') or '').strip()
    sort_order = int(body.get('sort_order', 0))
    return resource_service.create_type(name, sort_order).to_response()


@resource_bp.put('/types/<int:type_id>')
def update_type(type_id: int):
    err = _require_admin()
    if err: return err
    body = request.get_json() or {}
    kwargs = {}
    if 'name'       in body: kwargs['name']       = (body['name'] or '').strip()
    if 'sort_order' in body: kwargs['sort_order'] = int(body['sort_order'])
    return resource_service.update_type(type_id, **kwargs).to_response()


@resource_bp.delete('/types/<int:type_id>')
def delete_type(type_id: int):
    err = _require_admin()
    if err: return err
    return resource_service.delete_type(type_id).to_response()


# ── 资料条目 ──────────────────────────────────────────────────────────────

@resource_bp.get('')
def list_resources():
    type_id_raw = request.args.get('type_id', '')
    if type_id_raw == 'none':
        type_id = 'none'   # 查 type_id IS NULL
    elif type_id_raw:
        try: type_id = int(type_id_raw)
        except ValueError: type_id = None
    else:
        type_id = None
    search  = request.args.get('search', '').strip() or None
    page    = max(1, int(request.args.get('page', 1)))
    size    = max(1, min(100, int(request.args.get('size', 50))))
    return resource_service.list_resources(type_id, search, page, size).to_response()


@resource_bp.post('')
def create_resource():
    body = request.get_json() or {}
    title    = (body.get('title') or '').strip()
    url      = (body.get('url')   or '').strip()
    kwargs = {
        'type_id':           body.get('type_id'),
        'storage_key':       body.get('storage_key'),
        'source':            body.get('source', 'external'),
        'file_type':         body.get('file_type', 'link'),
        'original_filename': body.get('original_filename'),
        'description':       body.get('description'),
    }
    # 校验 file_type
    if kwargs['file_type'] not in VALID_FILE_TYPES:
        kwargs['file_type'] = 'other'
    return resource_service.create_resource(title, url, **kwargs).to_response()


@resource_bp.put('/<int:resource_id>')
def update_resource(resource_id: int):
    body   = request.get_json() or {}
    kwargs = {}
    for field in ('title', 'url', 'storage_key', 'source', 'file_type', 'original_filename', 'description'):
        if field in body:
            kwargs[field] = body[field]
    if 'type_id' in body:
        kwargs['type_id'] = body['type_id']
    if 'file_type' in kwargs and kwargs['file_type'] not in VALID_FILE_TYPES:
        kwargs['file_type'] = 'other'
    return resource_service.update_resource(resource_id, **kwargs).to_response()


@resource_bp.delete('/<int:resource_id>')
def delete_resource(resource_id: int):
    return resource_service.delete_resource(resource_id).to_response()


@resource_bp.put('/<int:resource_id>/models')
def set_resource_models(resource_id: int):
    body      = request.get_json() or {}
    model_ids = body.get('model_ids', [])
    if not isinstance(model_ids, list):
        return Result.fail('model_ids 必须为数组').to_response()
    return resource_service.set_resource_models(resource_id, model_ids).to_response()


@resource_bp.put('/<int:resource_id>/tags')
def set_resource_tags(resource_id: int):
    body    = request.get_json() or {}
    tag_ids = body.get('tag_ids', [])
    if not isinstance(tag_ids, list):
        return Result.fail('tag_ids 必须为数组').to_response()
    return resource_service.set_resource_tags(resource_id, tag_ids).to_response()


# ── 查看/下载签名 URL ─────────────────────────────────────────────────────

@resource_bp.get('/<int:resource_id>/signed-url')
def get_signed_url(resource_id: int):
    """为 OSS 资料生成带 response-content-disposition 的签名 GET URL。
    ?disposition=inline（默认）或 attachment
    """
    from services.product.resource import resource_service as _svc
    r = _svc.get_resource(resource_id)
    if not r.success:
        return r.to_response(404)
    resource = r.data
    storage_key = resource.get('storage_key') if isinstance(resource, dict) else None
    if not storage_key:
        # 外部链接直接返回原 URL
        url = resource.get('url') if isinstance(resource, dict) else resource_id
        return Result.ok(data={'url': url}).to_response()
    disposition = request.args.get('disposition', 'inline')
    if disposition not in ('inline', 'attachment'):
        disposition = 'inline'
    name = resource.get('original_filename') or resource.get('title') or 'file'
    cd = f'{disposition}; filename="{name}"'
    try:
        bucket = get_bucket()
        params = {'response-content-disposition': cd}
        content_type = _preview_content_type(resource)
        if disposition == 'inline' and content_type:
            params['response-content-type'] = content_type
        signed_url = bucket.sign_url('GET', storage_key, 3600, params=params)
        return Result.ok(data={'url': signed_url}).to_response()
    except Exception as e:
        return Result.fail(f'生成签名失败：{str(e)}').to_response()


# ── 预签名直传 ────────────────────────────────────────────────────────────

@resource_bp.post('/presign')
def presign_upload():
    """生成 OSS 预签名 PUT URL，前端直传文件到 OSS，避免经服务器中转。"""
    body = request.get_json() or {}
    ext  = (body.get('ext') or '').lower().lstrip('.')
    if ext not in UPLOAD_EXT_MAP:
        return Result.fail(f'不支持的文件类型: {ext}，支持: {", ".join(UPLOAD_EXT_MAP)}').to_response()

    content_type, file_type = UPLOAD_EXT_MAP[ext]
    yyyymm      = datetime.now().strftime('%Y%m')
    unique_name = f'{int(time.time())}_{uuid.uuid4().hex[:8]}.{ext}'
    rel_path    = f'resources/{yyyymm}/{unique_name}'
    key         = f'tmt-library/{rel_path}'

    try:
        bucket      = get_bucket()
        presign_url = bucket.sign_url('PUT', key, 3600, headers={'Content-Type': content_type})
        oss_url     = f'{OSS_BASE_URL}/{rel_path}'
        return Result.ok(data={
            'presign_url': presign_url,
            'oss_url':     oss_url,
            'storage_key': key,
            'file_type':   file_type,
        }).to_response()
    except Exception as e:
        return Result.fail(f'生成签名失败：{str(e)}').to_response()


# ── 产品-资料关联 ─────────────────────────────────────────────────────────

@resource_bp.get('/finished/<code>')
def get_product_resources(code: str):
    return resource_service.get_product_resources(code).to_response()


@resource_bp.post('/finished/<code>')
def link_resource(code: str):
    body        = request.get_json() or {}
    resource_id = body.get('resource_id')
    sort_order  = int(body.get('sort_order', 0))
    if not resource_id:
        return Result.fail('resource_id 不能为空').to_response()
    return resource_service.link_resource(code, resource_id, sort_order).to_response()


@resource_bp.delete('/finished/<code>/<int:resource_id>')
def unlink_resource(code: str, resource_id: int):
    return resource_service.unlink_resource(code, resource_id).to_response()


@resource_bp.put('/finished/<code>/order')
def update_order(code: str):
    body        = request.get_json() or {}
    ordered_ids = body.get('ordered_ids', [])
    if not isinstance(ordered_ids, list):
        return Result.fail('ordered_ids 必须为数组').to_response()
    return resource_service.update_order(code, ordered_ids).to_response()
