"""add customer alias to resolved shipping orders

Revision ID: 20260721_03
Revises: 20260721_02
Create Date: 2026-07-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20260721_03'
down_revision: Union[str, Sequence[str], None] = '20260721_02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table('shipping_order_finished'):
        return
    columns = {column['name'] for column in inspector.get_columns('shipping_order_finished')}
    if 'customer_alias' not in columns:
        op.add_column(
            'shipping_order_finished',
            sa.Column('customer_alias', sa.String(255), nullable=True),
        )
    indexes = {index['name'] for index in sa.inspect(connection).get_indexes('shipping_order_finished')}
    if 'ix_sof_source_customer_alias' not in indexes:
        op.create_index(
            'ix_sof_source_customer_alias',
            'shipping_order_finished',
            ['source', 'customer_alias'],
        )


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table('shipping_order_finished'):
        return
    indexes = {index['name'] for index in inspector.get_indexes('shipping_order_finished')}
    if 'ix_sof_source_customer_alias' in indexes:
        op.drop_index('ix_sof_source_customer_alias', table_name='shipping_order_finished')
    columns = {column['name'] for column in sa.inspect(connection).get_columns('shipping_order_finished')}
    if 'customer_alias' in columns:
        op.drop_column('shipping_order_finished', 'customer_alias')
