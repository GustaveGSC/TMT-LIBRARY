"""add data-configured finance dimension fields

Revision ID: 20260728_03
Revises: 20260728_02
Create Date: 2026-07-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20260728_03'
down_revision = '20260728_02'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if 'product_tag_category' not in set(inspect(bind).get_table_names()):
        return
    op.add_column(
        'product_tag_category',
        sa.Column('finance_dimension_field', sa.String(length=20), nullable=True),
    )
    op.execute(
        "UPDATE product_tag_category SET finance_dimension_field = 'country' "
        "WHERE name IN ('地域', '全球区域')"
    )
    op.execute(
        "UPDATE product_tag_category SET finance_dimension_field = 'brand' "
        "WHERE name = '品牌'"
    )


def downgrade():
    bind = op.get_bind()
    if 'product_tag_category' not in set(inspect(bind).get_table_names()):
        return
    columns = {column['name'] for column in inspect(bind).get_columns('product_tag_category')}
    if 'finance_dimension_field' in columns:
        op.drop_column('product_tag_category', 'finance_dimension_field')
