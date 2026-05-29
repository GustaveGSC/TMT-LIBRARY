import os
import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, g
from result import Result

SECRET_KEY   = os.environ.get('JWT_SECRET', 'tmt-dev-secret-change-in-production')
ALGORITHM    = 'HS256'
EXPIRE_DAYS  = 7


def generate_token(user: dict) -> str:
    """生成 JWT token，payload 含 id/username/roles/permissions。"""
    payload = {
        'id':          user['id'],
        'username':    user['username'],
        'roles':       user.get('roles', []),
        'permissions': user.get('permissions', []),
        'exp':         datetime.utcnow() + timedelta(days=EXPIRE_DAYS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> dict | None:
    """解码并校验 token，失败（过期/伪造/格式错误）返回 None。"""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


def has_permission(user: dict, perm: str) -> bool:
    """检查用户是否有指定权限；admin 角色直接通过。"""
    if 'admin' in user.get('roles', []):
        return True
    return perm in user.get('permissions', [])


def make_blueprint_guard(view_perm: str, edit_perm: str = None, export_perm: str = None):
    """
    生成蓝图 before_request 守卫函数，减少各蓝图重复代码。
    - view_perm:   所有请求需要的基础权限
    - edit_perm:   写操作（POST/PUT/DELETE/PATCH）需要的额外权限（可为 None 则不校验）
    - export_perm: 路径含 /export 的 POST 请求所需权限（优先于 edit_perm）
    """
    def guard():
        raw = request.headers.get('Authorization', '') or ''
        token = raw.removeprefix('Bearer ').strip()
        user = verify_token(token)
        if not user:
            return Result.fail('未登录或会话已过期').to_response(401)
        g.current_user = user
        if not has_permission(user, view_perm):
            return Result.fail('无访问权限').to_response(403)
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            if export_perm and '/export' in request.path:
                if not has_permission(user, export_perm):
                    return Result.fail('无导出权限').to_response(403)
            elif edit_perm:
                if not has_permission(user, edit_perm):
                    return Result.fail('无编辑权限').to_response(403)
    return guard


def require_auth(f):
    """路由装饰器：校验 Bearer token，成功后将用户信息写入 g.current_user。"""
    @wraps(f)
    def decorated(*args, **kwargs):
        raw = request.headers.get('Authorization', '') or ''
        token = raw.removeprefix('Bearer ').strip()
        user = verify_token(token)
        if not user:
            return Result.fail('未登录或会话已过期').to_response(401)
        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def is_rd_admin() -> bool:
    """在 @require_auth 之后调用，从 g.current_user 判断是否具备研发管理员权限。"""
    user = getattr(g, 'current_user', {})
    return 'admin' in user.get('roles', []) or 'rd:admin' in user.get('permissions', [])
