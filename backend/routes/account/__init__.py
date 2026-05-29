import os
import socket
from flask import Blueprint, request, g
from services.account import account_service
from auth import generate_token, verify_token
from result import Result

# 设置 ALLOW_REGISTER=false 可关闭公开注册（默认开启）
_ALLOW_REGISTER = os.environ.get('ALLOW_REGISTER', 'true').lower() not in ('false', '0', 'no')

def _machine_name():
    """返回当前机器主机名，作为游客/登录的身份标识"""
    try:
        return socket.gethostname()
    except Exception:
        return None

account_bp = Blueprint('account', __name__)

# login/guest/register 公开；change_password 任意登录用户；其余仅 admin
_ACCOUNT_PUBLIC       = frozenset({'account.login', 'account.guest_login', 'account.register'})
_ACCOUNT_SELF_ALLOWED = frozenset({'account.change_password'})

def _require_account_auth():
    """蓝图级鉴权：login/guest 公开；修改密码需登录；其余仅 admin 可操作。"""
    if request.endpoint in _ACCOUNT_PUBLIC:
        return None
    raw = request.headers.get('Authorization', '') or ''
    token = raw.removeprefix('Bearer ').strip()
    user = verify_token(token)
    if not user:
        return Result.fail('未登录或会话已过期').to_response(401)
    g.current_user = user
    if request.endpoint in _ACCOUNT_SELF_ALLOWED:
        return None
    if 'admin' not in user.get('roles', []):
        return Result.fail('权限不足，需要管理员权限').to_response(403)

account_bp.before_request(_require_account_auth)


# ── 登录 ──────────────────────────────────────────
@account_bp.post("/login")
def login():
    body     = request.get_json() or {}
    username = body.get("username", "").strip()
    password = body.get("password", "")
    if not username or not password:
        return Result.fail("用户名和密码不能为空").to_response()
    result = account_service.verify_password(username, password, machine_name=_machine_name())
    if result.success and result.data:
        result.data['token'] = generate_token(result.data)
    return result.to_response()


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
    # 非 admin 只能修改自己的密码
    current = g.current_user
    if 'admin' not in current.get('roles', []) and current.get('id') != user_id:
        return Result.fail("无权修改他人密码").to_response(403)
    return account_service.change_password(user_id, old_password, new_password).to_response()


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


# ── 游客登录 ──────────────────────────────────────
@account_bp.get("/guest")
def guest_login():
    result = account_service.guest_login(machine_name=_machine_name())
    if result.success and result.data:
        result.data['token'] = generate_token(result.data)
    return result.to_response()


# ── 登录记录与统计（author 专用）──────────────────
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


# ── 自助注册（公开，可通过 ALLOW_REGISTER=false 关闭）────
@account_bp.post("/register")
def register():
    if not _ALLOW_REGISTER:
        return Result.fail("注册功能已关闭，请联系管理员").to_response(403)
    body         = request.get_json() or {}
    username     = body.get("username",     "").strip()
    password     = body.get("password",     "")
    display_name = body.get("display_name", "").strip() or None
    if not username or not password:
        return Result.fail("用户名和密码不能为空").to_response()
    return account_service.create_user(username, password, display_name).to_response()
