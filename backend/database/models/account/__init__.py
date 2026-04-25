from datetime import datetime, timezone, timedelta
from database.base import db

_CST = timezone(timedelta(hours=8))
def _now_cst(): return datetime.now(_CST).replace(tzinfo=None)


# ── 用户-角色 关联表（多对多）────────────────────────
user_roles = db.Table(
    "user_roles",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id"), primary_key=True),
)

# ── 角色-权限 关联表（多对多）────────────────────────
role_permissions = db.Table(
    "role_permissions",
    db.Column("role_id",       db.Integer, db.ForeignKey("roles.id"),       primary_key=True),
    db.Column("permission_id", db.Integer, db.ForeignKey("permissions.id"), primary_key=True),
)


class User(db.Model):
    __tablename__ = "users"

    id         = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    username   = db.Column(db.String(64),  unique=True, nullable=False)
    password   = db.Column(db.String(255), nullable=False)          # bcrypt hash
    display_name = db.Column(db.String(64), nullable=True)
    is_active  = db.Column(db.Boolean,     default=True)
    created_at = db.Column(db.DateTime,    default=datetime.utcnow)
    updated_at = db.Column(db.DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)

    roles = db.relationship("Role", secondary=user_roles, backref="users", lazy="joined")

    def to_dict(self) -> dict:
        # 收集所有角色下的权限码（去重）
        perm_codes = list({
            p.code
            for r in self.roles
            for p in r.permissions
        })
        return {
            "id":           self.id,
            "username":     self.username,
            "display_name": self.display_name,
            "is_active":    self.is_active,
            "roles":        [r.name for r in self.roles],
            "permissions":  perm_codes,
            "created_at":   self.created_at.isoformat(),
        }


class Role(db.Model):
    __tablename__ = "roles"

    id          = db.Column(db.Integer,    primary_key=True, autoincrement=True)
    name        = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=True)

    permissions = db.relationship(
        "Permission", secondary=role_permissions, backref="roles", lazy="joined"
    )

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "name":        self.name,
            "description": self.description,
            "permissions": [p.code for p in self.permissions],
        }


class Permission(db.Model):
    __tablename__ = "permissions"

    id          = db.Column(db.Integer,    primary_key=True, autoincrement=True)
    code        = db.Column(db.String(64), unique=True, nullable=False)  # e.g. "product:edit"
    description = db.Column(db.String(255), nullable=True)

    def to_dict(self) -> dict:
        return {"id": self.id, "code": self.code, "description": self.description}


class UserLoginLog(db.Model):
    __tablename__ = "user_login_log"

    id           = db.Column(db.Integer,    primary_key=True, autoincrement=True)
    user_id      = db.Column(db.Integer,    db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    username     = db.Column(db.String(64), nullable=False)              # 登录时输入的用户名（游客为 'guest'）
    display_name = db.Column(db.String(64), nullable=True)              # 成功时记录显示名
    status       = db.Column(db.Enum("success", "failed"), nullable=False, default="success")
    machine_name = db.Column(db.String(128), nullable=True)             # 机器名/主机名，用于区分游客身份
    login_at     = db.Column(db.DateTime,   nullable=False, default=_now_cst)

    def to_dict(self) -> dict:
        return {
            "id":           self.id,
            "user_id":      self.user_id,
            "username":     self.username,
            "display_name": self.display_name,
            "status":       self.status,
            "machine_name": self.machine_name,
            "login_at":     self.login_at.isoformat() if self.login_at else None,
        }