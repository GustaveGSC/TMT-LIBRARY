import os
import socket
from flask import Blueprint, request, g, make_response
from services.account import account_service
from auth import get_request_user, has_permission, set_auth_cookies, clear_auth_cookies
from result import Result
from rate_limit import (
    LOGIN_ACCOUNT_LIMIT,
    LOGIN_ACCOUNT_SCOPE,
    LOGIN_IP_LIMIT,
    REGISTER_IP_LIMIT,
    clear_login_account_failures,
    deduct_failed_login,
    get_client_ip,
    get_login_username,
    limiter,
)

def _registration_enabled() -> bool:
    """公开注册默认关闭，仅在环境变量明确允许时开启。"""
    return os.environ.get('ALLOW_REGISTER', 'false').strip().lower() in ('true', '1', 'yes')

def _machine_name():
    """返回当前机器主机名，作为游客/登录的身份标识"""
    try:
        return socket.gethostname()
    except Exception:
        return None

account_bp = Blueprint('account', __name__)

# login/register/logout 公开；本人改密需登录；其余按端点权限矩阵。
_ACCOUNT_PUBLIC       = frozenset({
    'account.login', 'account.register', 'account.logout',
})
_ACCOUNT_SELF_ALLOWED = frozenset({'account.change_password'})
_ACCOUNT_ENDPOINT_PERMISSIONS = {
    'account.get_users': 'account:users:view',
    'account.create_user': 'account:users:edit',
    'account.update_user': 'account:users:edit',
    'account.delete_user': 'account:users:edit',
    'account.set_user_status': 'account:users:edit',
    'account.reset_password': 'account:users:edit',
    'account.assign_role': 'account:users:edit',
    'account.remove_role': 'account:users:edit',
    'account.get_roles': 'account:roles:view',
    'account.get_permissions': 'account:roles:view',
    'account.create_role': 'account:roles:edit',
    'account.delete_role': 'account:roles:edit',
    'account.assign_permission': 'account:roles:edit',
    'account.create_permission': 'account:roles:edit',
    'account.update_permission': 'account:roles:edit',
    'account.get_login_logs': 'developer:analytics:view',
    'account.get_login_dau': 'developer:analytics:view',
    'account.get_login_user_stats': 'developer:analytics:view',
}

def _require_account_auth():
    """蓝图级鉴权：认证后按端点映射检查显式权限码。"""
    if request.endpoint in _ACCOUNT_PUBLIC:
        return None
    if request.method == 'OPTIONS':
        return None
    user = get_request_user()
    if not user:
        return Result.fail('未登录或会话已过期').to_response(401)
    g.current_user = user
    if request.endpoint in _ACCOUNT_SELF_ALLOWED:
        return None
    required_permission = _ACCOUNT_ENDPOINT_PERMISSIONS.get(request.endpoint)
    if not required_permission or not has_permission(user, required_permission):
        return Result.fail('权限不足').to_response(403)

account_bp.before_request(_require_account_auth)


# ── 登录 ──────────────────────────────────────────
@account_bp.post("/login")
@limiter.limit(
    LOGIN_IP_LIMIT,
    key_func=get_client_ip,
    deduct_when=deduct_failed_login,
)
@limiter.shared_limit(
    LOGIN_ACCOUNT_LIMIT,
    scope=LOGIN_ACCOUNT_SCOPE,
    key_func=get_login_username,
    deduct_when=deduct_failed_login,
)
def login():
    body     = request.get_json() or {}
    username = body.get("username", "").strip()
    password = body.get("password", "")
    if not username or not password:
        return Result.fail("用户名和密码不能为空").to_response()
    result = account_service.verify_password(username, password, machine_name=_machine_name())
    if result.success and result.data:
        clear_login_account_failures(username)
        return set_auth_cookies(result.to_response(), result.data)
    return result.to_response()


@account_bp.post('/logout')
def logout():
    return clear_auth_cookies(Result.ok(message='已退出登录').to_response())


# ── 用户 CRUD ──────────────────────────────────────
@account_bp.get("/users")
def get_users():
    page     = request.args.get("page",     1,  type=int)
    per_page = request.args.get("per_page", 20, type=int)
    return account_service.get_users(page=page, per_page=per_page).to_response()


@account_bp.post("/users")
def create_user():
    body         = request.get_json() or {}
    username     = body.get("username",     "").strip()
    password     = body.get("password",     "")
    display_name = body.get("display_name", "").strip() or None
    if not username or not password:
        return Result.fail("用户名和密码不能为空").to_response()
    return account_service.create_user(username, password, display_name).to_response()


@account_bp.put("/users/<int:user_id>")
def update_user(user_id):
    body = request.get_json() or {}
    return account_service.update_user(user_id, **body).to_response()


@account_bp.delete("/users/<int:user_id>")
def delete_user(user_id):
    return account_service.delete_user(user_id).to_response()


# ── 密码 ──────────────────────────────────────────
@account_bp.put("/users/<int:user_id>/password")
def change_password(user_id):
    body         = request.get_json() or {}
    old_password = body.get("old_password", "")
    new_password = body.get("new_password", "")
    if not old_password or not new_password:
        return Result.fail("原密码和新密码不能为空").to_response()
    # 本人可改自己的密码；管理者可操作他人账号。
    current = g.current_user
    if (
        current.get('id') != user_id
        and not has_permission(current, 'account:users:edit')
    ):
        return Result.fail("无权修改他人密码").to_response(403)
    result = account_service.change_password(user_id, old_password, new_password)
    response = make_response(result.to_response())
    if result.success and current.get('id') == user_id:
        return clear_auth_cookies(response)
    return response


@account_bp.put("/users/<int:user_id>/status")
def set_user_status(user_id):
    body      = request.get_json() or {}
    is_active = body.get("is_active")
    if is_active is None:
        return Result.fail("缺少 is_active 参数").to_response()
    return account_service.set_user_status(user_id, bool(is_active)).to_response()


@account_bp.post("/users/<int:user_id>/reset-password")
def reset_password(user_id):
    body         = request.get_json() or {}
    new_password = body.get("new_password", "")
    if not new_password:
        return Result.fail("新密码不能为空").to_response()
    return account_service.reset_password(user_id, new_password).to_response()


# ── 角色分配 ──────────────────────────────────────
@account_bp.post("/users/<int:user_id>/roles/<int:role_id>")
def assign_role(user_id, role_id):
    return account_service.assign_role(user_id, role_id).to_response()


@account_bp.delete("/users/<int:user_id>/roles/<int:role_id>")
def remove_role(user_id, role_id):
    return account_service.remove_role(user_id, role_id).to_response()


# ── 角色管理 ──────────────────────────────────────
@account_bp.get("/roles")
def get_roles():
    return account_service.get_roles().to_response()


@account_bp.post("/roles")
def create_role():
    body        = request.get_json() or {}
    name        = body.get("name",        "").strip()
    description = body.get("description", "").strip() or None
    if not name:
        return Result.fail("角色名不能为空").to_response()
    return account_service.create_role(name, description).to_response()


@account_bp.delete("/roles/<int:role_id>")
def delete_role(role_id):
    return account_service.delete_role(role_id).to_response()


@account_bp.post("/roles/<int:role_id>/permissions/<string:code>")
def assign_permission(role_id, code):
    return account_service.assign_permission_to_role(role_id, code).to_response()


# ── 登录记录与统计（developer:analytics:view）──────
@account_bp.get("/login-logs")
def get_login_logs():
    page     = request.args.get("page",     1,  type=int)
    per_page = request.args.get("per_page", 50, type=int)
    username = request.args.get("username", "").strip() or None
    return account_service.get_login_logs(page=page, per_page=per_page, username=username).to_response()

@account_bp.get("/login-stats/dau")
def get_login_dau():
    days = request.args.get("days", 30, type=int)
    return account_service.get_login_dau(days=days).to_response()

@account_bp.get("/login-stats/users")
def get_login_user_stats():
    return account_service.get_login_user_stats().to_response()


# ── 权限管理 ──────────────────────────────────────
@account_bp.get("/permissions")
def get_permissions():
    return account_service.get_permissions().to_response()


@account_bp.post("/permissions")
def create_permission():
    body        = request.get_json() or {}
    code        = body.get("code",        "").strip()
    name        = body.get("name",        "").strip() or None
    description = body.get("description", "").strip() or None
    if not code:
        return Result.fail("权限码不能为空").to_response()
    return account_service.create_permission(code, name, description).to_response()


@account_bp.put("/permissions/<int:perm_id>")
def update_permission(perm_id):
    body = request.get_json() or {}
    return account_service.update_permission(perm_id, **body).to_response()


# ── 自助注册（公开，默认关闭）─────────────────────────
@account_bp.post("/register")
@limiter.limit(
    REGISTER_IP_LIMIT,
    key_func=get_client_ip,
    exempt_when=lambda: not _registration_enabled(),
)
def register():
    if not _registration_enabled():
        return Result.fail("注册功能已关闭，请联系管理员").to_response(403)
    body         = request.get_json() or {}
    username     = body.get("username",     "").strip()
    password     = body.get("password",     "")
    display_name = body.get("display_name", "").strip() or None
    if not username or not password:
        return Result.fail("用户名和密码不能为空").to_response()
    return account_service.create_user(username, password, display_name).to_response()
