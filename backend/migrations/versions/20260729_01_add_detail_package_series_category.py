"""add product detail package series and category scopes

Revision ID: 20260729_01
Revises: 20260728_03
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa


revision = '20260729_01'
down_revision = '20260728_03'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'product_detail_package_series',
        sa.Column('package_id', sa.Integer(), sa.ForeignKey('product_detail_package.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('series_id', sa.Integer(), sa.ForeignKey('product_series.id', ondelete='CASCADE'), primary_key=True),
    )
    op.create_table(
        'product_detail_package_category',
        sa.Column('package_id', sa.Integer(), sa.ForeignKey('product_detail_package.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('category_id', sa.Integer(), sa.ForeignKey('product_category.id', ondelete='CASCADE'), primary_key=True),
    )


def downgrade():
    op.drop_table('product_detail_package_category')
    op.drop_table('product_detail_package_series')
