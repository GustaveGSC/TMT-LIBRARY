import os
import hmac
import secrets
import jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, g, make_response, current_app
from result import Result
from security_config import is_production_environment

SECRET_KEY   = os.environ.get('JWT_SECRET', 'tmt-dev-secret-change-in-production')
ALGORITHM    = 'HS256'
EXPIRE_DAYS  = 7
COOKIE_MAX_AGE = EXPIRE_DAYS * 24 * 60 * 60
SESSION_COOKIE = 'tmt_session'
CSRF_COOKIE = 'tmt_csrf'
CSRF_HEADER = 'X-CSRF-Token'
_SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})
_CSRF_EXEMPT_ENDPOINTS = frozenset({
    'account.login', 'account.register',
})


def generate_token(user: dict, csrf_token: str | None = None) -> str:
    """生成 JWT token，payload 含 id/username/roles/permissions。"""
    payload = {
        'id':          user['id'],
        'username':    user['username'],
        'roles':       user.get('roles', []),
        'permissions': user.get('permissions', []),
        'ver':         int(user.get('token_version', 0) or 0),
        'csrf':        csrf_token,
        'exp':         datetime.now(timezone.utc) + timedelta(days=EXPIRE_DAYS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _cookie_options(*, httponly: bool) -> dict:
    return {
        'path': '/',
        'secure': is_production_environment(),
        'httponly': httponly,
        'samesite': 'Strict',
    }


def set_auth_cookies(response, user: dict):
    """签发相互绑定的会话与 CSRF Cookie。"""
    response = make_response(response)
    csrf_token = secrets.token_urlsafe(32)
    session_token = generate_token(user, csrf_token=csrf_token)
    expires = datetime.now(timezone.utc) + timedelta(seconds=COOKIE_MAX_AGE)
    response.set_cookie(
        SESSION_COOKIE, session_token, max_age=COOKIE_MAX_AGE, expires=expires,
        **_cookie_options(httponly=True),
    )
    response.set_cookie(
        CSRF_COOKIE, csrf_token, max_age=COOKIE_MAX_AGE, expires=expires,
        **_cookie_options(httponly=False),
    )
    return response


def clear_auth_cookies(response):
    response = make_response(response)
    response.delete_cookie(SESSION_COOKIE, **_cookie_options(httponly=True))
    response.delete_cookie(CSRF_COOKIE, **_cookie_options(httponly=False))
    return response


def clear_auth_cookies_on_unauthorized(response):
    """所有 401 响应统一删除浏览器中的失效会话。"""
    if response.status_code == 401:
        return clear_auth_cookies(response)
    return response


def verify_token(token: str) -> dict | None:
    """校验签名、账号状态和 token 版本；失效统一返回 None。"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    token_version = payload.get('ver')
    user_id = payload.get('id')
    if user_id is None:
        return None
    if token_version is None:
        return None
    from database.repository.account import UserRepository
    state = UserRepository.get_auth_state(user_id)
    if not state:
        return None
    is_active, current_version = state
    if not is_active or token_version != current_version:
        return None
    return payload


def get_request_user() -> dict | None:
    """从 httpOnly Cookie 读取并校验会话；同一请求只查询一次账号状态。"""
    if hasattr(g, '_verified_session_user'):
        return g._verified_session_user
    token = request.cookies.get(SESSION_COOKIE, '')
    user = verify_token(token) if token else None
    g._verified_session_user = user
    return user


def validate_csrf_request():
    """有效会话的非安全方法必须携带与 JWT 绑定的双提交 CSRF token。"""
    if request.method in _SAFE_METHODS or request.endpoint in _CSRF_EXEMPT_ENDPOINTS:
        return None
    user = get_request_user()
    if not user:
        return None
    header_token = request.headers.get(CSRF_HEADER, '')
    cookie_token = request.cookies.get(CSRF_COOKIE, '')
    claim_token = user.get('csrf') or ''
    if not all((header_token, cookie_token, claim_token)) or not (
        hmac.compare_digest(header_token, cookie_token)
        and hmac.compare_digest(header_token, claim_token)
    ):
        return Result.fail('CSRF 校验失败').to_response(403)
    return None


def has_permission(user: dict, perm: str) -> bool:
    """只根据显式权限码授权；角色名和用户名不构成功能授权。"""
    return perm in user.get('permissions', [])


def make_blueprint_guard(view_perm: str, edit_perm: str = None, export_perm: str = None,
                         view_post_paths: tuple = (), public_paths: tuple = ()):
    """
    生成蓝图 before_request 守卫函数，减少各蓝图重复代码。
    - view_perm:        所有请求需要的基础权限
    - edit_perm:        写操作（POST/PUT/DELETE/PATCH）需要的额外权限（可为 None 则不校验）
    - export_perm:      路径含 /export 的 POST 请求所需权限（优先于 edit_perm）
    - view_post_paths:  POST 路径后缀白名单，匹配则只需 view_perm（查询型 POST 接口用）
    - public_paths:     完全公开的路径后缀白名单，跳过所有鉴权
    """
    def guard():
        if request.method == 'OPTIONS':
            return None
        if public_paths and any(request.path.endswith(p) for p in public_paths):
            return None
        user = get_request_user()
        if not user:
            return Result.fail('未登录或会话已过期').to_response(401)
        g.current_user = user
        if not has_permission(user, view_perm):
            return Result.fail('无访问权限').to_response(403)
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            # 只读 POST 接口（如图表查询）跳过编辑权限检查
            if view_post_paths and any(request.path.endswith(p) for p in view_post_paths):
                return None
            if export_perm and '/export' in request.path:
                if not has_permission(user, export_perm):
                    return Result.fail('无导出权限').to_response(403)
            elif edit_perm:
                if not has_permission(user, edit_perm):
                    return Result.fail('无编辑权限').to_response(403)
    return guard


def require_auth(f):
    """路由装饰器：校验 Cookie 会话，成功后将用户信息写入 g.current_user。"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'OPTIONS':
            return current_app.make_default_options_response()
        user = get_request_user()
        if not user:
            return Result.fail('未登录或会话已过期').to_response(401)
        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def is_rd_admin() -> bool:
    """在 @require_auth 之后调用，从 g.current_user 判断是否具备研发管理员权限。"""
    user = getattr(g, 'current_user', {})
    return has_permission(user, 'rd:admin')
