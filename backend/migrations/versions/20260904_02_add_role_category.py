"""add roles.category (system/department/function), backfill existing roles

Revision ID: 20260904_02
Revises: 20260904_01
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa

revision = '20260904_02'
down_revision = '20260904_01'
branch_labels = None
depends_on = None

# 和 src/views/adminViews/page-permissions.vue 里原来纯前端的 roleGroupOf() 名字规律一致，
# 迁移时按同一套规则回填，避免上线瞬间所有角色分类"归零"
SYSTEM_ROLE_NAMES = ('admin', '管理员', 'developer', 'manager', 'ops')


def upgrade():
    op.add_column(
        'roles',
        sa.Column('category', sa.String(20), nullable=False, server_default='function'),
    )
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE roles SET category = 'system' WHERE name IN :names"
        ).bindparams(sa.bindparam('names', expanding=True)),
        {'names': list(SYSTEM_ROLE_NAMES)},
    )
    connection.execute(
        sa.text("UPDATE roles SET category = 'department' WHERE name LIKE '%部%' AND category != 'system'")
    )
    # 其余角色保持列默认值 'function'，无需再更新


def downgrade():
    op.drop_column('roles', 'category')
