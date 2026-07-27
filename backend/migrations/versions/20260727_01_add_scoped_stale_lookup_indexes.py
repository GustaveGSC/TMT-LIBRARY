"""add lookup indexes for scoped shipping stale markers

Revision ID: 20260727_01
Revises: 20260726_01
Create Date: 2026-07-27
"""

from alembic import op
from sqlalchemy import inspect


revision = '20260727_01'
down_revision = '20260726_01'
branch_labels = None
depends_on = None


def upgrade():
    # Keep the live and next generations index-identical: cutover uses RENAME
    # TABLE, so the next generation becomes the live table without rebuilding.
    existing = set(inspect(op.get_bind()).get_table_names())
    for table_name in ('shipping_order_finished', 'shipping_order_finished_next'):
        if table_name in existing:
            op.create_index(
                'ix_sof_source_order', table_name,
                ['source', 'ecommerce_order_no'],
            )
    if 'return_record' in existing:
        op.create_index(
            'ix_return_record_warehouse_order', 'return_record',
            ['warehouse_name', 'ecommerce_order_no'],
        )


def downgrade():
    existing = set(inspect(op.get_bind()).get_table_names())
    if 'return_record' in existing:
        op.drop_index('ix_return_record_warehouse_order', table_name='return_record')
    for table_name in ('shipping_order_finished_next', 'shipping_order_finished'):
        if table_name in existing:
            op.drop_index('ix_sof_source_order', table_name=table_name)
