"""replace finance export flag with review status

Revision ID: 20260721_04
Revises: 20260721_03
Create Date: 2026-07-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20260721_04'
down_revision: Union[str, Sequence[str], None] = '20260721_03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table('shipping_finance_customer_mapping'):
        return
    columns = {column['name'] for column in inspector.get_columns('shipping_finance_customer_mapping')}
    if 'status' not in columns:
        op.add_column(
            'shipping_finance_customer_mapping',
            sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        )
    if 'is_export' in columns:
        connection.execute(sa.text("""
            UPDATE shipping_finance_customer_mapping
            SET status = CASE WHEN is_export THEN 'export' ELSE 'non_sales' END
        """))
        op.drop_column('shipping_finance_customer_mapping', 'is_export')


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table('shipping_finance_customer_mapping'):
        return
    columns = {column['name'] for column in inspector.get_columns('shipping_finance_customer_mapping')}
    if 'is_export' not in columns:
        op.add_column(
            'shipping_finance_customer_mapping',
            sa.Column('is_export', sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if 'status' in columns:
        connection.execute(sa.text("""
            UPDATE shipping_finance_customer_mapping
            SET is_export = CASE WHEN status = 'export' THEN 1 ELSE 0 END
        """))
        op.drop_column('shipping_finance_customer_mapping', 'status')
