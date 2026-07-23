import bcrypt
from sqlalchemy.exc import IntegrityError

from database.base import db
from database.repository.account import UserRepository, RoleRepository, PermissionRepository, LoginLogRepository
from result import Result


MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_BYTES = 72
MAX_USERNAME_LENGTH = 64
MAX_DISPLAY_NAME_LENGTH = 64
_DUMMY_PASSWORD_HASH = b"$2b$12$yn369zGOz9RgxI.UJnOhJOkffgSSEMIXEorNXdLZRLs0Jo8haRbq6"


def _password_error(password, label: str = "密码"):
    if not isinstance(password, str):
        return f"{label}格式不正确"
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"{label}至少 {MIN_PASSWORD_LENGTH} 位"
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return f"{label}不能超过 {MAX_PASSWORD_BYTES} 字节"
    return None


def _username_error(username):
    if not isinstance(username, str) or not username.strip():
        return "用户名不能为空"
    if len(username.strip()) > MAX_USERNAME_LENGTH:
        return f"用户名不能超过 {MAX_USERNAME_LENGTH} 个字符"
    return None


def _display_name_error(display_name):
    if display_name is None:
        return None
    if not isinstance(display_name, str):
        return "显示名称格式不正确"
    if len(display_name.strip()) > MAX_DISPLAY_NAME_LENGTH:
        return f"显示名称不能超过 {MAX_DISPLAY_NAME_LENGTH} 个字符"
    return None


class AccountService:

    # ── 用户 ─────────────────────────────────────────
    def get_user(self, user_id: int) -> Result:
        user = UserRepository.get_by_id(user_id)
        if not user:
            return Result.fail(f"用户 {user_id} 不存在")
        return Result.ok(user.to_dict())

    def get_users(self, page: int = 1, per_page: int = 20) -> Result:
        return Result.ok(UserRepository.get_all(page=page, per_page=per_page))

    def create_user(self, username: str, password: str, display_name: str = None) -> Result:
        if error := _username_error(username):
            return Result.fail(error)
        if error := _password_error(password):
            return Result.fail(error)
        if error := _display_name_error(display_name):
            return Result.fail(error)
        username = username.strip()
        display_name = display_name.strip() if display_name else None
        if UserRepository.get_by_username(username):
            return Result.fail(f"用户名 '{username}' 已存在")
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        try:
            user = UserRepository.create(username, password_hash, display_name)
        except IntegrityError:
            db.session.rollback()
            return Result.fail(f"用户名 '{username}' 已存在")
        return Result.ok(user.to_dict(), message="用户创建成功")

    def update_user(self, user_id: int, **kwargs) -> Result:
        user = UserRepository.get_by_id(user_id)
        if not user:
            return Result.fail(f"用户 {user_id} 不存在")
        if "username" in kwargs:
            if error := _username_error(kwargs["username"]):
                return Result.fail(error)
            kwargs["username"] = kwargs["username"].strip()
        if "display_name" in kwargs:
            if error := _display_name_error(kwargs["display_name"]):
                return Result.fail(error)
            if isinstance(kwargs["display_name"], str):
                kwargs["display_name"] = kwargs["display_name"].strip() or None
        password_changed = "password" in kwargs
        status_changed = "is_active" in kwargs and kwargs["is_active"] is not None
        if password_changed:
            if error := _password_error(kwargs["password"]):
                return Result.fail(error)
            kwargs["password"] = bcrypt.hashpw(
                kwargs["password"].encode(), bcrypt.gensalt()
            ).decode()
        try:
            updated = UserRepository.update(
                user,
                invalidate_tokens=password_changed or status_changed,
                **kwargs,
            )
        except IntegrityError:
            db.session.rollback()
            return Result.fail(f"用户名 '{kwargs.get('username')}' 已存在")
        return Result.ok(updated.to_dict(), message="更新成功")

    def delete_user(self, user_id: int) -> Result:
        user = UserRepository.get_by_id(user_id)
        if not user:
            return Result.fail(f"用户 {user_id} 不存在")
        if user.username in ('admin', 'author'):
            return Result.fail(f"用户 '{user.username}' 不可删除")
        UserRepository.delete(user)
        return Result.ok(message="删除成功")

    def verify_password(self, username: str, password: str, machine_name: str = None) -> Result:
        user = UserRepository.get_by_username(username)
        if not user:
            bcrypt.checkpw(
                password.encode() if isinstance(password, str) and len(password.encode()) <= MAX_PASSWORD_BYTES else b"invalid",
                _DUMMY_PASSWORD_HASH,
            )
            LoginLogRepository.create(username=username, status='failed', machine_name=machine_name)
            return Result.fail("用户名或密码错误")
        password_bytes = password.encode() if isinstance(password, str) else b""
        if len(password_bytes) > MAX_PASSWORD_BYTES:
            bcrypt.checkpw(b"invalid", _DUMMY_PASSWORD_HASH)
            password_matches = False
        else:
            password_matches = bcrypt.checkpw(password_bytes, user.password.encode())
        if not password_matches:
            LoginLogRepository.create(username=username, status='failed', user_id=user.id,
                                      display_name=user.display_name, machine_name=machine_name)
            return Result.fail("用户名或密码错误")
        if not user.is_active:
            LoginLogRepository.create(username=username, status='failed', user_id=user.id,
                                      display_name=user.display_name, machine_name=machine_name)
            return Result.fail("账号已被禁用")
        LoginLogRepository.create(username=username, status='success', user_id=user.id,
                                  display_name=user.display_name, machine_name=machine_name)
        return Result.ok(user.to_dict())

    def change_password(self, user_id: int, old_password: str, new_password: str) -> Result:
        user = UserRepository.get_by_id(user_id)
        if not user:
            return Result.fail("用户不存在")
        if not bcrypt.checkpw(old_password.encode(), user.password.encode()):
            return Result.fail("原密码错误")
        if error := _password_error(new_password, "新密码"):
            return Result.fail(error)
        new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        UserRepository.update(user, invalidate_tokens=True, password=new_hash)
        return Result.ok(message="密码修改成功")

    def set_user_status(self, user_id: int, is_active: bool) -> Result:
        user = UserRepository.get_by_id(user_id)
        if not user:
            return Result.fail("用户不存在")
        if user.username in ('admin', 'author'):
            return Result.fail(f"用户 '{user.username}' 不可禁用")
        UserRepository.update(user, invalidate_tokens=True, is_active=is_active)
        return Result.ok(message="状态更新成功")

    def reset_password(self, user_id: int, new_password: str) -> Result:
        user = UserRepository.get_by_id(user_id)
        if not user:
            return Result.fail("用户不存在")
        if error := _password_error(new_password, "新密码"):
            return Result.fail(error)
        new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        UserRepository.update(user, invalidate_tokens=True, password=new_hash)
        return Result.ok(message="密码重置成功")

    # ── 角色分配 ──────────────────────────────────────
    def assign_role(self, user_id: int, role_id: int) -> Result:
        user = UserRepository.get_by_id(user_id)
        role = RoleRepository.get_by_id(role_id)
        if not user: return Result.fail(f"用户 {user_id} 不存在")
        if not role: return Result.fail(f"角色 {role_id} 不存在")
        UserRepository.assign_role(user, role)
        return Result.ok(message="角色分配成功")

    def remove_role(self, user_id: int, role_id: int) -> Result:
        user = UserRepository.get_by_id(user_id)
        role = RoleRepository.get_by_id(role_id)
        if not user or not role: return Result.fail("用户或角色不存在")
        UserRepository.remove_role(user, role)
        return Result.ok(message="角色移除成功")

    # ── 角色管理 ──────────────────────────────────────
    def get_roles(self) -> Result:
        return Result.ok([r.to_dict() for r in RoleRepository.get_all()])

    def create_role(self, name: str, description: str = None) -> Result:
        if RoleRepository.get_by_name(name):
            return Result.fail(f"角色 '{name}' 已存在")
        return Result.ok(RoleRepository.create(name, description).to_dict(), message="角色创建成功")

    def delete_role(self, role_id: int) -> Result:
        role = RoleRepository.get_by_id(role_id)
        if not role: return Result.fail(f"角色 {role_id} 不存在")
        RoleRepository.delete(role)
        return Result.ok(message="角色删除成功")

    # ── 权限管理 ──────────────────────────────────────
    def get_permissions(self) -> Result:
        return Result.ok([p.to_dict() for p in PermissionRepository.get_all()])

    def create_permission(self, code: str, name: str = None, description: str = None) -> Result:
        if PermissionRepository.get_by_code(code):
            return Result.fail(f"权限 '{code}' 已存在")
        return Result.ok(
            PermissionRepository.create(code, name, description).to_dict(),
            message="权限创建成功"
        )

    def update_permission(self, perm_id: int, **kwargs) -> Result:
        perm = PermissionRepository.get_by_id(perm_id)
        if not perm: return Result.fail(f"权限 {perm_id} 不存在")
        return Result.ok(PermissionRepository.update(perm, **kwargs).to_dict(), message="更新成功")

    def get_login_logs(self, page: int = 1, per_page: int = 50, username: str = None) -> Result:
        return Result.ok(LoginLogRepository.get_all(page=page, per_page=per_page, username=username))

    def get_login_dau(self, days: int = 30) -> Result:
        return Result.ok(LoginLogRepository.get_dau(days=days))

    def get_login_user_stats(self) -> Result:
        return Result.ok(LoginLogRepository.get_user_stats())

    def assign_permission_to_role(self, role_id: int, permission_code: str) -> Result:
        role = RoleRepository.get_by_id(role_id)
        permission = PermissionRepository.get_by_code(permission_code)
        if not role: return Result.fail(f"角色 {role_id} 不存在")
        if not permission: return Result.fail(f"权限 '{permission_code}' 不存在")
        RoleRepository.assign_permission(role, permission)
        return Result.ok(message="权限分配成功")


account_service = AccountService()
