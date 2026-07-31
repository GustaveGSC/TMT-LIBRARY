"""align material join key collations

Revision ID: 20260731_02
Revises: 20260731_01
Create Date: 2026-07-31

生产历史表 import_product_raw 的 JOIN 键使用 utf8mb4_0900_ai_ci，而新表最初
继承数据库默认 utf8mb4_unicode_ci。仅对齐两张新表的键，避免重写历史业务表。
"""

from alembic import op


revision = '20260731_02'
down_revision = '20260731_01'
branch_labels = None
depends_on = None


def _is_mysql():
    return op.get_bind().dialect.name == 'mysql'


def upgrade():
    if not _is_mysql():
        return
    op.execute(
        'ALTER TABLE product_material '
        'MODIFY code VARCHAR(255) CHARACTER SET utf8mb4 '
        'COLLATE utf8mb4_0900_ai_ci NOT NULL'
    )
    op.execute(
        'ALTER TABLE erp_group_category '
        'MODIFY group_code VARCHAR(64) CHARACTER SET utf8mb4 '
        'COLLATE utf8mb4_0900_ai_ci NOT NULL'
    )


def downgrade():
    if not _is_mysql():
        return
    op.execute(
        'ALTER TABLE product_material '
        'MODIFY code VARCHAR(255) CHARACTER SET utf8mb4 '
        'COLLATE utf8mb4_unicode_ci NOT NULL'
    )
    op.execute(
        'ALTER TABLE erp_group_category '
        'MODIFY group_code VARCHAR(64) CHARACTER SET utf8mb4 '
        'COLLATE utf8mb4_unicode_ci NOT NULL'
    )
