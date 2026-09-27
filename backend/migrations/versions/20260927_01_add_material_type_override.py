"""add type_override column to product material

Revision ID: 20260927_01
Revises: 20260926_01
Create Date: 2026-09-27
"""

from alembic import op
import sqlalchemy as sa


revision = '20260927_01'
down_revision = '20260926_01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'product_material',
        sa.Column('type_override', sa.String(length=100), nullable=True),
    )


def downgrade():
    op.drop_column('product_material', 'type_override')
