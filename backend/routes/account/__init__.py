from flask import Blueprint, request
from services.account import account_service
from result import Result

account_bp = Blueprint('account', __name__)


# ── 登录 ──────────────────────────────────────────
@account_bp.post("/login")
def login():
    body     = request.get_json() or {}
    username = body.get("username", "").strip()
    password = body.get("password", "")
    if not username or not password:
        return Result.fail("用户名和密码不能为空").to_response()
    return account_service.verify_password(username, password).to_response()


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
    return account_service.guest_login().to_response()


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
