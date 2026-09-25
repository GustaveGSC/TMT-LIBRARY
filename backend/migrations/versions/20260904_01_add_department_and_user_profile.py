"""add departments table, users.department_id/employee_no, ops:department:edit permission

Revision ID: 20260904_01
Revises: 20260819_01
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa

revision = '20260904_01'
down_revision = '20260819_01'
branch_labels = None
depends_on = None

PERMISSION_CODE = 'ops:department:edit'
PERMISSION_NAME = '部门管理'
PERMISSION_DESC = '新增/编辑/删除部门'


def upgrade():
    op.create_table(
        'departments',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('name', name='uq_departments_name'),
    )
    op.add_column('users', sa.Column('department_id', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('employee_no', sa.String(32), nullable=True))
    op.create_foreign_key(
        'fk_users_department_id', 'users', 'departments',
        ['department_id'], ['id'], ondelete='SET NULL',
    )

    connection = op.get_bind()
    inspector = sa.inspect(connection)
    required_tables = {'roles', 'permissions', 'role_permissions'}
    if not required_tables.issubset(inspector.get_table_names()):
        return

    connection.execute(
        sa.text(
            "INSERT INTO permissions (code, name, description) "
            "SELECT :code, :name, :description WHERE NOT EXISTS ("
            "SELECT 1 FROM permissions WHERE code = :code)"
        ),
        {'code': PERMISSION_CODE, 'name': PERMISSION_NAME, 'description': PERMISSION_DESC},
    )
    # 与既有 ops:login-config:edit 一致，绑定给 ops 和 admin 两个角色
    connection.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT r.id, p.id FROM roles r JOIN permissions p "
            "ON p.code = :code WHERE r.name IN ('ops', 'admin') AND NOT EXISTS ("
            "SELECT 1 FROM role_permissions rp "
            "WHERE rp.role_id = r.id AND rp.permission_id = p.id)"
        ),
        {'code': PERMISSION_CODE},
    )
    connection.execute(
        sa.text(
            "UPDATE users SET token_version = token_version + 1 WHERE id IN ("
            "SELECT ur.user_id FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
            "WHERE r.name IN ('ops', 'admin'))"
        )
    )


def downgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if {'roles', 'permissions', 'role_permissions'}.issubset(inspector.get_table_names()):
        connection.execute(
            sa.text(
                "DELETE FROM role_permissions WHERE permission_id IN ("
                "SELECT id FROM permissions WHERE code = :code)"
            ),
            {'code': PERMISSION_CODE},
        )
        connection.execute(
            sa.text("DELETE FROM permissions WHERE code = :code"),
            {'code': PERMISSION_CODE},
        )
    op.drop_constraint('fk_users_department_id', 'users', type_='foreignkey')
    op.drop_column('users', 'employee_no')
    op.drop_column('users', 'department_id')
    op.drop_table('departments')
