from typing import Optional
from database.base import db
from database.models.account import User, Role, Permission


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