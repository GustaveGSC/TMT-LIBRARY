from typing import Optional
from database.base import db
from database.models.account import User, Role, Permission, UserLoginLog, _now_cst


class UserRepository:

    @staticmethod
    def get_by_id(user_id: int) -> Optional[User]:
        return db.session.get(User, user_id)

    @staticmethod
    def get_by_username(username: str) -> Optional[User]:
        return User.query.filter_by(username=username).first()

    @staticmethod
    def get_all(page: int = 1, per_page: int = 20) -> dict:
        pagination = User.query.order_by(User.id).paginate(
            page=page, per_page=per_page, error_out=False
        )
        return {
            "items": [u.to_dict() for u in pagination.items],
            "total": pagination.total,
            "page":  pagination.page,
            "pages": pagination.pages,
        }

    @staticmethod
    def create(username: str, password_hash: str, display_name: str = None) -> User:
        user = User(username=username, password=password_hash, display_name=display_name)
        db.session.add(user)
        db.session.commit()
        return user

    @staticmethod
    def update(user: User, **kwargs) -> User:
        for key, value in kwargs.items():
            if hasattr(user, key) and value is not None:
                setattr(user, key, value)
        db.session.commit()
        return user

    @staticmethod
    def delete(user: User) -> None:
        db.session.delete(user)
        db.session.commit()

    @staticmethod
    def assign_role(user: User, role: Role) -> None:
        if role not in user.roles:
            user.roles.append(role)
            db.session.commit()

    @staticmethod
    def remove_role(user: User, role: Role) -> None:
        if role in user.roles:
            user.roles.remove(role)
            db.session.commit()


class RoleRepository:

    @staticmethod
    def get_by_id(role_id: int) -> Optional[Role]:
        return db.session.get(Role, role_id)

    @staticmethod
    def get_by_name(name: str) -> Optional[Role]:
        return Role.query.filter_by(name=name).first()

    @staticmethod
    def get_all() -> list:
        return Role.query.order_by(Role.id).all()

    @staticmethod
    def create(name: str, description: str = None) -> Role:
        role = Role(name=name, description=description)
        db.session.add(role)
        db.session.commit()
        return role

    @staticmethod
    def update(role: Role, **kwargs) -> Role:
        for key, value in kwargs.items():
            if hasattr(role, key) and value is not None:
                setattr(role, key, value)
        db.session.commit()
        return role

    @staticmethod
    def delete(role: Role) -> None:
        db.session.delete(role)
        db.session.commit()

    @staticmethod
    def assign_permission(role: Role, permission: Permission) -> None:
        if permission not in role.permissions:
            role.permissions.append(permission)
            db.session.commit()


class LoginLogRepository:

    @staticmethod
    def create(username: str, status: str, user_id: int = None,
               display_name: str = None, machine_name: str = None) -> UserLoginLog:
        log = UserLoginLog(
            user_id      = user_id,
            username     = username,
            display_name = display_name,
            status       = status,
            machine_name = machine_name,
            login_at     = _now_cst(),
        )
        db.session.add(log)
        db.session.commit()
        return log

    @staticmethod
    def get_all(page: int = 1, per_page: int = 50, username: str = None) -> dict:
        q = UserLoginLog.query
        if username:
            q = q.filter(UserLoginLog.username.ilike(f'%{username}%'))
        q = q.order_by(UserLoginLog.login_at.desc())
        pagination = q.paginate(page=page, per_page=per_page, error_out=False)
        return {
            "items": [r.to_dict() for r in pagination.items],
            "total": pagination.total,
            "page":  pagination.page,
            "pages": pagination.pages,
        }

    @staticmethod
    def get_dau(days: int = 30) -> list:
        """按天统计日活（distinct 用户身份：注册用户用 user_id，游客用 machine_name），仅计成功登录"""
        sql = db.text("""
            SELECT
                DATE(login_at) AS date,
                COUNT(DISTINCT
                    CASE
                        WHEN user_id IS NOT NULL THEN CONCAT('u_', user_id)
                        ELSE CONCAT('g_', IFNULL(machine_name, 'unknown'))
                    END
                ) AS count
            FROM user_login_log
            WHERE status = 'success'
              AND login_at >= DATE_SUB(NOW(), INTERVAL :days DAY)
            GROUP BY DATE(login_at)
            ORDER BY date
        """)
        rows = db.session.execute(sql, {'days': days}).fetchall()
        return [{'date': str(r.date), 'count': int(r.count)} for r in rows]

    @staticmethod
    def get_user_stats() -> list:
        """
        每个"用户身份"的登录统计：
        - 注册用户：按 user_id 聚合
        - 游客：按 machine_name 聚合，username 显示为 '游客 (machine_name)'
        """
        # 注册用户
        sql_users = db.text("""
            SELECT
                username,
                display_name,
                COUNT(*)                             AS total,
                SUM(status = 'success')              AS success_count,
                SUM(status = 'failed')               AS failed_count,
                MAX(login_at)                        AS last_login_at,
                'user'                               AS identity_type
            FROM user_login_log
            WHERE user_id IS NOT NULL
            GROUP BY user_id, username, display_name
            ORDER BY last_login_at DESC
        """)
        # 游客（按 machine_name 分组）
        sql_guests = db.text("""
            SELECT
                CONCAT('游客 (', IFNULL(machine_name, 'unknown'), ')') AS username,
                NULL                                                    AS display_name,
                COUNT(*)                                                AS total,
                COUNT(*)                                                AS success_count,
                0                                                       AS failed_count,
                MAX(login_at)                                           AS last_login_at,
                'guest'                                                 AS identity_type
            FROM user_login_log
            WHERE username = 'guest'
            GROUP BY machine_name
            ORDER BY last_login_at DESC
        """)
        def _row(r, t):
            return {
                'username':      r.username,
                'display_name':  r.display_name,
                'total':         int(r.total),
                'success_count': int(r.success_count),
                'failed_count':  int(r.failed_count),
                'last_login_at': r.last_login_at.isoformat() if r.last_login_at else None,
                'identity_type': t,
            }
        users  = [_row(r, 'user')  for r in db.session.execute(sql_users).fetchall()]
        guests = [_row(r, 'guest') for r in db.session.execute(sql_guests).fetchall()]
        return users + guests


class PermissionRepository:

    @staticmethod
    def get_all() -> list:
        return Permission.query.order_by(Permission.code).all()

    @staticmethod
    def get_by_id(perm_id: int) -> Optional[Permission]:
        return db.session.get(Permission, perm_id)

    @staticmethod
    def get_by_code(code: str) -> Optional[Permission]:
        return Permission.query.filter_by(code=code).first()

    @staticmethod
    def create(code: str, name: str = None, description: str = None) -> Permission:
        permission = Permission(code=code, name=name, description=description)
        db.session.add(permission)
        db.session.commit()
        return permission

    @staticmethod
    def update(perm: Permission, **kwargs) -> Permission:
        for key, value in kwargs.items():
            if hasattr(perm, key):
                setattr(perm, key, value)
        db.session.commit()
        return perm