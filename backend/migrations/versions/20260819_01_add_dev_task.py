"""add dev_task table and developer:tasks:view permission

Revision ID: 20260819_01
Revises: 20260818_01
Create Date: 2026-08-19
"""

from alembic import op
import sqlalchemy as sa

revision = '20260819_01'
down_revision = '20260818_01'
branch_labels = None
depends_on = None

PERMISSION_CODE = 'developer:tasks:view'
PERMISSION_NAME = '开发任务'
PERMISSION_DESC = '查看/创建/编辑/关闭开发任务'


def upgrade():
    op.create_table(
        'dev_task',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('priority', sa.String(10), nullable=False, server_default='medium'),
        sa.Column('status', sa.String(10), nullable=False, server_default='open'),
        sa.Column('created_by', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('closed_by', sa.String(64), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_dev_task_status', 'dev_task', ['status'])

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
    connection.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT r.id, p.id FROM roles r JOIN permissions p "
            "ON p.code = :code WHERE r.name = 'developer' AND NOT EXISTS ("
            "SELECT 1 FROM role_permissions rp "
            "WHERE rp.role_id = r.id AND rp.permission_id = p.id)"
        ),
        {'code': PERMISSION_CODE},
    )
    # legacy admin 显式绑定全部权限，含本次新增项。
    connection.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT r.id, p.id FROM roles r CROSS JOIN permissions p "
            "WHERE r.name = 'admin' AND p.code = :code AND NOT EXISTS ("
            "SELECT 1 FROM role_permissions rp "
            "WHERE rp.role_id = r.id AND rp.permission_id = p.id)"
        ),
        {'code': PERMISSION_CODE},
    )
    # JWT 内嵌权限；使 developer/admin 角色下的账号重新登录后取得新权限。
    connection.execute(
        sa.text(
            "UPDATE users SET token_version = token_version + 1 WHERE id IN ("
            "SELECT ur.user_id FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
            "WHERE r.name IN ('developer', 'admin'))"
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
    op.drop_index('ix_dev_task_status', table_name='dev_task')
    op.drop_table('dev_task')
