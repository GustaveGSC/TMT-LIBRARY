"""add shipping resolve staging tables

Revision ID: 20260725_01
Revises: 20260724_03
Create Date: 2026-07-25
"""

from alembic import op
import sqlalchemy as sa


revision = '20260725_01'
down_revision = '20260724_03'
branch_labels = None
depends_on = None


source_enum = sa.Enum('shipping', 'finance', name='shipping_source')


def upgrade():
    op.create_table(
        'shipping_resolve_target',
        sa.Column('task_id', sa.String(36), nullable=False),
        sa.Column('source', source_enum, nullable=False),
        sa.Column('ecommerce_order_no', sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint(
            'task_id', 'source', 'ecommerce_order_no',
            name='pk_shipping_resolve_target',
        ),
    )
    op.create_table(
        'shipping_order_finished_staging',
        sa.Column(
            'id',
            sa.BigInteger().with_variant(sa.Integer(), 'sqlite'),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column('task_id', sa.String(36), nullable=False),
        sa.Column('ecommerce_order_no', sa.String(100), nullable=False),
        sa.Column('finished_code', sa.String(100), nullable=True),
        sa.Column('finished_name', sa.String(255), nullable=True),
        sa.Column('quantity', sa.Numeric(12, 2), nullable=True),
        sa.Column('return_quantity', sa.Numeric(12, 2), nullable=True),
        sa.Column('actual_quantity', sa.Numeric(12, 2), nullable=True),
        sa.Column('shipped_date', sa.Date(), nullable=True),
        sa.Column('operator', sa.String(100), nullable=True),
        sa.Column('channel_name', sa.String(100), nullable=True),
        sa.Column('channel_code', sa.String(100), nullable=True),
        sa.Column('channel_org_name', sa.String(100), nullable=True),
        sa.Column('province', sa.String(50), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('district', sa.String(100), nullable=True),
        sa.Column('customer_alias', sa.String(255), nullable=True),
        sa.Column('source', source_enum, nullable=False),
        sa.Column('is_stale', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_sofs_task_source_order',
        'shipping_order_finished_staging',
        ['task_id', 'source', 'ecommerce_order_no'],
    )


def downgrade():
    op.drop_table('shipping_order_finished_staging')
    op.drop_table('shipping_resolve_target')
