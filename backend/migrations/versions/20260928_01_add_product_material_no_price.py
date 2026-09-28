"""add product_material.no_price (不计价标记)

客供件、赠送件等永远不会有采购价的物料，标记后计价按 0 元、算作已有价格；
否则用到它的部件永远到不了「下级价格齐全」、无法开始计价。

Revision ID: 20260928_01
Revises: 20260927_04
Create Date: 2026-09-28
"""

from alembic import op
import sqlalchemy as sa


revision = '20260928_01'
down_revision = '20260927_04'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('product_material') as batch:
        batch.add_column(sa.Column('no_price', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('product_material') as batch:
        batch.drop_column('no_price')
