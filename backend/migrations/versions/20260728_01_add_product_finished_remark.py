"""add product finished remark

Revision ID: 20260728_01
Revises: 20260727_02
Create Date: 2026-07-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20260728_01'
down_revision = '20260727_02'
branch_labels = None
depends_on = None


def upgrade():
    # Baseline tests intentionally start from an empty schema; production has
    # product_finished from the stamped baseline and must receive the column.
    tables = set(inspect(op.get_bind()).get_table_names())
    if 'product_finished' in tables:
        op.add_column('product_finished', sa.Column('remark', sa.Text(), nullable=True))


def downgrade():
    bind = op.get_bind()
    if 'product_finished' in set(inspect(bind).get_table_names()):
        columns = {column['name'] for column in inspect(bind).get_columns('product_finished')}
        if 'remark' in columns:
            op.drop_column('product_finished', 'remark')
