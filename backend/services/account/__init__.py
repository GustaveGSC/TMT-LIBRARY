import bcrypt
from database.repository.account import UserRepository, RoleRepository, PermissionRepository
from result import Result


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
        if UserRepository.get_by_username(username):
            return Result.fail(f"用户名 '{username}' 已存在")
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        user = UserRepository.create(username, password_hash, display_name)
        # 新用户自动绑定内置游客角色
        guest_role = RoleRepository.get_by_name("guest")
        if guest_role:
            UserRepository.assign_role(user, guest_role)
        return Result.ok(user.to_dict(), message="用户创建成功")

    def update_user(self, user_id: int, **kwargs) -> Result:
        user = UserRepository.get_by_id(user_id)
        if not user:
            return Result.fail(f"用户 {user_id} 不存在")
        if "password" in kwargs and kwargs["password"]:
            kwargs["password"] = bcrypt.hashpw(
                kwargs["password"].encode(), bcrypt.gensalt()
            ).decode()
        return Result.ok(UserRepository.update(user, **kwargs).to_dict(), message="更新成功")

    def delete_user(self, user_id: int) -> Result:
        user = UserRepository.get_by_id(user_id)
        if not user:
            return Result.fail(f"用户 {user_id} 不存在")
        UserRepository.delete(user)
        return Result.ok(message="删除成功")

    def verify_password(self, username: str, password: str) -> Result:
        user = UserRepository.get_by_username(username)
        if not user:
            return Result.fail("用户名或密码错误")
        if not bcrypt.checkpw(password.encode(), user.password.encode()):
            return Result.fail("用户名或密码错误")
        if not user.is_active:
            return Result.fail("账号已被禁用")
        return Result.ok(user.to_dict())

    def change_password(self, user_id: int, old_password: str, new_password: str) -> Result:
        user = UserRepository.get_by_id(user_id)
        if not user:
            return Result.fail("用户不存在")
        if not bcrypt.checkpw(old_password.encode(), user.password.encode()):
            return Result.fail("原密码错误")
        if len(new_password) < 6:
            return Result.fail("新密码至少 6 位")
        new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        UserRepository.update(user, password=new_hash)
        return Result.ok(message="密码修改成功")

    def set_user_status(self, user_id: int, is_active: bool) -> Result:
        user = UserRepository.get_by_id(user_id)
        if not user:
            return Result.fail("用户不存在")
        UserRepository.update(user, is_active=is_active)
        return Result.ok(message="状态更新成功")

    def reset_password(self, user_id: int, new_password: str) -> Result:
        user = UserRepository.get_by_id(user_id)
        if not user:
            return Result.fail("用户不存在")
        new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        UserRepository.update(user, password=new_hash)
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

    def guest_login(self) -> Result:
        """返回游客身份信息，权限取自 guest 角色"""
        guest_role = RoleRepository.get_by_name("guest")
        perm_codes = [p.code for p in guest_role.permissions] if guest_role else []
        return Result.ok({
            "id":           None,
            "username":     "guest",
            "display_name": "游客",
            "is_active":    True,
            "roles":        ["guest"],
            "permissions":  perm_codes,
            "created_at":   None,
        })

    def assign_permission_to_role(self, role_id: int, permission_code: str) -> Result:
        role = RoleRepository.get_by_id(role_id)
        permission = PermissionRepository.get_by_code(permission_code)
        if not role: return Result.fail(f"角色 {role_id} 不存在")
        if not permission: return Result.fail(f"权限 '{permission_code}' 不存在")
        RoleRepository.assign_permission(role, permission)
        return Result.ok(message="权限分配成功")


account_service = AccountService()
