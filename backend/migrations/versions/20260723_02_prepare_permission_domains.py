"""prepare explicit developer, manager and ops permission domains

Revision ID: 20260723_02
Revises: 20260723_01
Create Date: 2026-07-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20260723_02'
down_revision: Union[str, Sequence[str], None] = '20260723_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PERMISSIONS = (
    ('developer:analytics:view', '查看用户分析', '查看登录日志、DAU 和用户登录统计'),
    ('account:users:view', '查看用户', '查看用户列表和用户详情'),
    ('account:users:edit', '管理用户', '创建、编辑、禁用、删除、重置密码和分配角色'),
    ('account:roles:view', '查看角色权限', '查看角色和权限清单'),
    ('account:roles:edit', '管理角色权限', '创建删除角色、维护权限项和调整角色权限'),
    ('ops:login-config:edit', '管理登录页配置', '修改登录页轮播文案'),
)

STANDARD_ROLES = (
    ('developer', '开发者——查看用户分析'),
    ('manager', '管理者——管理用户、角色和权限'),
    ('ops', '运维——维护运行配置'),
)

ROLE_PERMISSION_CODES = {
    'developer': ('developer:analytics:view',),
    'manager': (
        'account:users:view',
        'account:users:edit',
        'account:roles:view',
        'account:roles:edit',
    ),
    'ops': ('ops:login-config:edit',),
}


def _insert_role_permission(connection, role_name: str, permission_code: str) -> None:
    connection.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT r.id, p.id FROM roles r JOIN permissions p "
            "ON p.code = :permission_code "
            "WHERE r.name = :role_name AND NOT EXISTS ("
            "SELECT 1 FROM role_permissions rp "
            "WHERE rp.role_id = r.id AND rp.permission_id = p.id)"
        ),
        {'role_name': role_name, 'permission_code': permission_code},
    )


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    required_tables = {'users', 'roles', 'permissions', 'user_roles', 'role_permissions'}
    if not required_tables.issubset(inspector.get_table_names()):
        return

    for code, name, description in PERMISSIONS:
        connection.execute(
            sa.text(
                "INSERT INTO permissions (code, name, description) "
                "SELECT :code, :name, :description WHERE NOT EXISTS ("
                "SELECT 1 FROM permissions WHERE code = :code)"
            ),
            {'code': code, 'name': name, 'description': description},
        )

    for name, description in STANDARD_ROLES:
        connection.execute(
            sa.text(
                "INSERT INTO roles (name, description) "
                "SELECT :name, :description WHERE NOT EXISTS ("
                "SELECT 1 FROM roles WHERE name = :name)"
            ),
            {'name': name, 'description': description},
        )

    for role_name, permission_codes in ROLE_PERMISSION_CODES.items():
        for permission_code in permission_codes:
            _insert_role_permission(connection, role_name, permission_code)

    # legacy admin 先显式绑定当前全部权限；第二批移除代码级 admin 绕过后行为不变。
    connection.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT r.id, p.id FROM roles r CROSS JOIN permissions p "
            "WHERE r.name = 'admin' AND NOT EXISTS ("
            "SELECT 1 FROM role_permissions rp "
            "WHERE rp.role_id = r.id AND rp.permission_id = p.id)"
        )
    )

    # author 只做加法迁移，不撤销其既有角色，避免未审计生产关联时意外撤权。
    connection.execute(
        sa.text(
            "INSERT INTO user_roles (user_id, role_id) "
            "SELECT u.id, r.id FROM users u CROSS JOIN roles r "
            "WHERE u.username = 'author' AND r.name = 'developer' "
            "AND NOT EXISTS (SELECT 1 FROM user_roles ur "
            "WHERE ur.user_id = u.id AND ur.role_id = r.id)"
        )
    )

    # JWT 内嵌角色/权限；使受本迁移影响的账号重新登录并取得显式权限集合。
    connection.execute(
        sa.text(
            "UPDATE users SET token_version = token_version + 1 "
            "WHERE username = 'author' OR id IN ("
            "SELECT ur.user_id FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
            "WHERE r.name = 'admin')"
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    required_tables = {'roles', 'permissions', 'user_roles', 'role_permissions'}
    if not required_tables.issubset(inspector.get_table_names()):
        return

    permission_codes = tuple(code for code, _name, _description in PERMISSIONS)
    role_names = tuple(name for name, _description in STANDARD_ROLES)

    connection.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN ("
            "SELECT id FROM permissions WHERE code IN :permission_codes)"
        ).bindparams(sa.bindparam('permission_codes', expanding=True)),
        {'permission_codes': permission_codes},
    )
    connection.execute(
        sa.text(
            "DELETE FROM user_roles WHERE role_id IN ("
            "SELECT id FROM roles WHERE name IN :role_names)"
        ).bindparams(sa.bindparam('role_names', expanding=True)),
        {'role_names': role_names},
    )
    connection.execute(
        sa.text("DELETE FROM permissions WHERE code IN :permission_codes").bindparams(
            sa.bindparam('permission_codes', expanding=True)
        ),
        {'permission_codes': permission_codes},
    )
    connection.execute(
        sa.text("DELETE FROM roles WHERE name IN :role_names").bindparams(
            sa.bindparam('role_names', expanding=True)
        ),
        {'role_names': role_names},
    )
