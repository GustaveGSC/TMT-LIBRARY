"""add shipping generation tables for atomic rename cutover

Revision ID: 20260726_01
Revises: 20260725_01
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa


revision = '20260726_01'
down_revision = '20260725_01'
branch_labels = None
depends_on = None


source_enum = sa.Enum('shipping', 'finance', name='shipping_source')


def _create_finished_generation_table():
    op.create_table(
        'shipping_order_finished_next',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
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
        sa.Column('is_stale', sa.Boolean(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    indexes = (
        ('ix_sof_order_no', ('ecommerce_order_no',)),
        ('ix_sof_shipped_date', ('shipped_date',)),
        ('ix_sof_operator', ('operator',)),
        ('ix_sof_province', ('province',)),
        ('ix_sof_source', ('source',)),
        ('ix_sof_source_date', ('source', 'shipped_date')),
        ('ix_sof_source_finished_code', ('source', 'finished_code')),
        ('ix_sof_source_customer_alias', ('source', 'customer_alias')),
        ('ix_sof_finished_code_date', ('finished_code', 'shipped_date')),
    )
    for name, columns in indexes:
        op.create_index(name, 'shipping_order_finished_next', list(columns))


def _create_marker_table(name):
    op.create_table(
        name,
        sa.Column('id', sa.SmallInteger(), nullable=False),
        sa.Column('task_id', sa.String(36), nullable=True),
        sa.Column('row_count', sa.BigInteger(), nullable=True),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.bulk_insert(
        sa.table(
            name,
            sa.column('id', sa.SmallInteger()),
            sa.column('task_id', sa.String(36)),
            sa.column('row_count', sa.BigInteger()),
            sa.column('published_at', sa.DateTime()),
        ),
        [{
            'id': 1,
            'task_id': None,
            'row_count': None,
            'published_at': None,
        }],
    )


def upgrade():
    if op.get_bind().dialect.name == 'mysql':
        # Preserve the production table's exact collation, row format,
        # defaults and performance-critical index names.
        op.execute(
            'CREATE TABLE shipping_order_finished_next '
            'LIKE shipping_order_finished'
        )
    else:
        _create_finished_generation_table()
    _create_marker_table('shipping_order_finished_generation')
    _create_marker_table('shipping_order_finished_generation_next')


def downgrade():
    op.drop_table('shipping_order_finished_generation_next')
    op.drop_table('shipping_order_finished_generation')
    op.drop_table('shipping_order_finished_next')
