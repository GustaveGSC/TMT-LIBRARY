"""add product lifecycle task

Revision ID: 20260724_02
Revises: 20260724_01
Create Date: 2026-07-24
"""

from alembic import op
import sqlalchemy as sa


revision = '20260724_02'
down_revision = '20260724_01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'product_lifecycle_task',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('progress', sa.JSON(), nullable=True),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('lease_key', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lease_key', name='uq_product_lifecycle_task_lease_key'),
    )
    op.create_index(
        'ix_product_lifecycle_task_status_updated',
        'product_lifecycle_task',
        ['status', 'updated_at'],
        unique=False,
    )


def downgrade():
    op.drop_index(
        'ix_product_lifecycle_task_status_updated',
        table_name='product_lifecycle_task',
    )
    op.drop_table('product_lifecycle_task')
