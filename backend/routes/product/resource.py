import os
import uuid
import time
import hmac
import hashlib
from datetime import datetime

from flask import Blueprint, request, g, Response
from services.product.resource import resource_service
from storage.client import get_bucket
from auth import make_blueprint_guard
from result import Result

SHARE_SECRET = os.getenv('SHARE_SECRET', 'tmt-share-key-2024')
SHARE_TTL    = 7 * 24 * 3600   # 7 天


def _make_share_token(resource_id: int, exp: int) -> str:
    msg = f"{resource_id}:{exp}"
    return hmac.new(SHARE_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()[:24]


def _verify_share_token(resource_id: int, exp: int, key: str) -> bool:
    if int(time.time()) > exp:
        return False
    expected = _make_share_token(resource_id, exp)
    return hmac.compare_digest(expected, key)

resource_bp = Blueprint('resource', __name__)
resource_bp.before_request(make_blueprint_guard('product:view', 'product:edit', public_paths=('/share-page', '/proxy-content', '/og-image')))

OSS_BASE_URL = os.getenv('OSS_BASE_URL', '').rstrip('/')

VALID_FILE_TYPES = {'pdf', 'image', 'video', 'link', 'other'}
UPLOAD_EXT_MAP = {
    'pdf':  ('application/pdf',       'pdf'),
    'png':  ('image/png',             'image'),
    'jpg':  ('image/jpeg',            'image'),
    'jpeg': ('image/jpeg',            'image'),
    'webp': ('image/webp',            'image'),
    'mp4':  ('video/mp4',             'video'),
    'mov':  ('video/quicktime',       'video'),
    'webm': ('video/webm',            'video'),
}
PREVIEW_CONTENT_TYPES = {
    'pdf':  'application/pdf',
    'png':  'image/png',
    'jpg':  'image/jpeg',
    'jpeg': 'image/jpeg',
    'webp': 'image/webp',
    'mp4':  'video/mp4',
    'mov':  'video/quicktime',
    'webm': 'video/webm',
}
VIDEO_EXTS = {'mp4', 'mov', 'webm'}


def _preview_content_type(resource: dict) -> str | None:
    file_type = resource.get('file_type')
    if file_type == 'pdf':
        return PREVIEW_CONTENT_TYPES['pdf']
    filename = resource.get('original_filename') or resource.get('storage_key') or resource.get('url') or ''
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if file_type in ('image', 'video'):
        return PREVIEW_CONTENT_TYPES.get(ext)
    return None


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
        'cover_storage_key': body.get('cover_storage_key'),
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
    for field in ('title', 'url', 'storage_key', 'cover_storage_key', 'source', 'file_type', 'original_filename', 'description'):
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
    try:
        expiry = max(60, min(604800, int(request.args.get('expiry', 3600))))
    except (ValueError, TypeError):
        expiry = 3600
    name = resource.get('original_filename') or resource.get('title') or 'file'
    cd = f'{disposition}; filename="{name}"'
    try:
        bucket = get_bucket()
        params = {'response-content-disposition': cd}
        content_type = _preview_content_type(resource)
        if disposition == 'inline' and content_type:
            params['response-content-type'] = content_type
        signed_url = bucket.sign_url('GET', storage_key, expiry, params=params)
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
        bucket  = get_bucket()
        headers = {'Content-Type': content_type}
        if ext in VIDEO_EXTS:
            headers['Cache-Control'] = 'max-age=2592000'
        presign_url = bucket.sign_url('PUT', key, 3600, headers=headers)
        oss_url     = f'{OSS_BASE_URL}/{rel_path}'
        return Result.ok(data={
            'presign_url': presign_url,
            'oss_url':     oss_url,
            'storage_key': key,
            'file_type':   file_type,
        }).to_response()
    except Exception as e:
        return Result.fail(f'生成签名失败：{str(e)}').to_response()


# ── OG 封面代理（供分享链接预览，无需登录）──────────────────────────────

@resource_bp.get('/<int:resource_id>/og-image')
def og_image(resource_id: int):
    """代理资料封面图或图片本身，供 og:image 爬取（inline 返回，无强制下载）。"""
    r = resource_service.get_resource(resource_id)
    if not r.success:
        return Response('not found', status=404)
    resource    = r.data
    file_type   = resource.get('file_type')
    # 封面图优先，其次图片本身
    if file_type == 'image':
        storage_key = resource.get('storage_key')
    else:
        # video 等：用 cover_storage_key
        storage_key = resource.get('cover_storage_key')
    if not storage_key:
        return Response('no image', status=404)
    try:
        bucket = get_bucket()
        obj    = bucket.get_object(storage_key)
        data   = obj.read()
        ext    = storage_key.rsplit('.', 1)[-1].lower()
        ct_map = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'webp': 'image/webp'}
        content_type = ct_map.get(ext, 'image/jpeg')
        return Response(data, mimetype=content_type, headers={
            'Content-Disposition': 'inline',
            'Cache-Control': 'public, max-age=86400',
        })
    except Exception as e:
        return Response(str(e), status=500)


# ── 分享链接 ─────────────────────────────────────────────────────────────

@resource_bp.get('/<int:resource_id>/proxy-content')
def proxy_content(resource_id: int):
    """代理 OSS 资料内容，供分享页 PDF.js 同源拉取（绕过 CORS）。"""
    key = request.args.get('key', '')
    try:
        exp = int(request.args.get('exp', 0))
    except (ValueError, TypeError):
        exp = 0
    if not _verify_share_token(resource_id, exp, key):
        return Response('链接已过期或无效', status=403, mimetype='text/plain')
    r = resource_service.get_resource(resource_id)
    if not r.success:
        return Response('资料不存在', status=404, mimetype='text/plain')
    resource    = r.data
    storage_key = resource.get('storage_key')
    if not storage_key:
        from flask import redirect
        return redirect(resource.get('url', ''), code=302)
    try:
        bucket       = get_bucket()
        obj          = bucket.get_object(storage_key)
        data         = obj.read()
        content_type = _preview_content_type(resource) or 'application/octet-stream'
        filename     = resource.get('original_filename') or resource.get('title') or 'file'
        return Response(
            data,
            mimetype=content_type,
            headers={
                'Content-Disposition': f'inline; filename="{filename}"',
                'Cache-Control': 'private, max-age=3600',
                'Access-Control-Allow-Origin': '*',
            }
        )
    except Exception as e:
        import traceback; traceback.print_exc()
        return Response(str(e), status=500, mimetype='text/plain')


@resource_bp.get('/<int:resource_id>/share')
def get_share_link(resource_id: int):
    """生成带 HMAC token 的分享页面链接（需登录，有效期 7 天）。"""
    r = resource_service.get_resource(resource_id)
    if not r.success:
        return r.to_response(404)
    exp = int(time.time()) + SHARE_TTL
    key = _make_share_token(resource_id, exp)
    base = request.host_url.rstrip('/')
    share_url = f'{base}/api/resources/{resource_id}/share-page?key={key}&exp={exp}'
    return Result.ok(data={'url': share_url}).to_response()


@resource_bp.get('/<int:resource_id>/share-page')
def share_page(resource_id: int):
    """无需登录的分享页面，校验 token 后返回内嵌播放器的 HTML。"""
    key = request.args.get('key', '')
    try:
        exp = int(request.args.get('exp', 0))
    except ValueError:
        exp = 0
    if not _verify_share_token(resource_id, exp, key):
        return Response('<h3 style="font-family:sans-serif;text-align:center;margin-top:80px">链接已过期或无效</h3>', status=403, mimetype='text/html')

    r = resource_service.get_resource(resource_id)
    if not r.success:
        return Response('<h3 style="font-family:sans-serif;text-align:center;margin-top:80px">资料不存在</h3>', status=404, mimetype='text/html')
    resource = r.data
    title    = resource.get('title', '资料')
    file_type = resource.get('file_type', 'link')
    storage_key = resource.get('storage_key')

    # 生成可访问 URL
    if storage_key:
        try:
            bucket  = get_bucket()
            ct      = _preview_content_type(resource)
            params  = {'response-content-disposition': f'inline; filename="{resource.get("original_filename") or title}"'}
            if ct:
                params['response-content-type'] = ct
            media_url = bucket.sign_url('GET', storage_key, 3600, params=params)
        except Exception:
            media_url = resource.get('url', '')
    else:
        media_url = resource.get('url', '')

    html_title = title.replace('<', '&lt;').replace('>', '&gt;')
    media_url_esc = media_url.replace('"', '&quot;')

    # Open Graph meta：让聊天软件显示缩略图
    # 用代理接口返回 inline 图片（OSS bucket 强制下载，直接用 OSS URL 爬虫无法预览）
    proto     = request.headers.get('X-Forwarded-Proto', request.scheme)
    base_url  = f"{proto}://{request.host}"
    share_url = f"{base_url}{request.full_path}"
    og_image  = ''
    if file_type == 'image':
        og_image = f'{base_url}/api/resources/{resource_id}/og-image'
    elif file_type == 'video' and resource.get('cover_storage_key'):
        og_image = f'{base_url}/api/resources/{resource_id}/og-image'

    if file_type == 'video':
        body = f'''
<style>
  body{{margin:0;background:#000;display:flex;align-items:center;justify-content:center;min-height:100vh}}
  video{{width:100%;max-height:100vh;outline:none}}
</style>
<video src="{media_url_esc}" controls autoplay playsinline webkit-playsinline preload="auto"></video>'''
    elif file_type == 'image':
        body = f'''
<style>
  body{{margin:0;background:#111;display:flex;align-items:center;justify-content:center;min-height:100vh}}
  img{{max-width:100%;max-height:100vh;object-fit:contain}}
</style>
<img src="{media_url_esc}" alt="{html_title}">'''
    elif file_type == 'pdf':
        proxy_url = f'/api/resources/{resource_id}/proxy-content?key={key}&exp={exp}'
        filename_esc = (resource.get('original_filename') or title).replace('"', '&quot;')
        body = f'''
<style>
  body{{margin:0;background:#525659;font-family:sans-serif}}
  #pages{{display:flex;flex-direction:column;align-items:center;padding:8px;gap:8px}}
  canvas{{max-width:100%;display:block;box-shadow:0 2px 8px rgba(0,0,0,.4)}}
  #msg{{color:#fff;text-align:center;padding:50px 20px;font-size:15px;line-height:1.8}}
  #msg a{{color:#f0c060;font-size:14px}}
</style>
<div id="msg">PDF 加载中…<br><a id="dl" href="{proxy_url}" download="{filename_esc}" style="display:none">加载失败？点此下载 PDF</a></div>
<div id="pages"></div>
<script>
var PDFJS_CDN='https://registry.npmmirror.com/pdfjs-dist/3.11.174/files/build/';
var t=setTimeout(function(){{document.getElementById('dl').style.display='inline'}},8000);
var s=document.createElement('script');
s.src=PDFJS_CDN+'pdf.min.js';
s.onerror=function(){{clearTimeout(t);document.getElementById('msg').innerHTML='PDF 加载失败，请<a href="{proxy_url}" download="{filename_esc}">点此下载</a>';}}
s.onload=function(){{
  pdfjsLib.GlobalWorkerOptions.workerSrc=PDFJS_CDN+'pdf.worker.min.js';
  pdfjsLib.getDocument('{proxy_url}').promise.then(function(pdf){{
    clearTimeout(t);
    document.getElementById('msg').style.display='none';
    var pages=document.getElementById('pages');
    var w=window.innerWidth-16;
    for(var i=1;i<=pdf.numPages;i++){{
      (function(n){{pdf.getPage(n).then(function(page){{
        var vp=page.getViewport({{scale:w/page.getViewport({{scale:1}}).width}});
        var canvas=document.createElement('canvas');
        canvas.width=vp.width;canvas.height=vp.height;
        page.render({{canvasContext:canvas.getContext('2d'),viewport:vp}});
        pages.appendChild(canvas);
      }})}})(i);
    }}
  }}).catch(function(e){{
    clearTimeout(t);
    document.getElementById('msg').innerHTML='加载失败：'+e.message+'<br><a href="{proxy_url}" download="{filename_esc}">点此下载 PDF</a>';
  }});
}};
document.head.appendChild(s);
</script>'''
    else:
        body = f'<script>location.href="{media_url_esc}"</script>'

    og_image_tag = f'<meta property="og:image" content="{og_image.replace(chr(34), "&quot;")}">\n' if og_image else ''
    html = f'''<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<title>{html_title}</title>
<meta property="og:title" content="{html_title}">
<meta property="og:type" content="website">
<meta property="og:url" content="{share_url.replace(chr(34), '&quot;')}">
{og_image_tag}<meta name="twitter:card" content="{'summary_large_image' if og_image else 'summary'}">
<meta name="twitter:title" content="{html_title}">
{f'<meta name="twitter:image" content="{og_image.replace(chr(34), chr(39))}">' if og_image else ''}
</head>
<body>
{body}
</body>
</html>'''
    return Response(html, mimetype='text/html')


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
