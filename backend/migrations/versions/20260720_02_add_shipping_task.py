"""add persistent shipping task state

Revision ID: 20260720_02
Revises: 20260720_01
Create Date: 2026-07-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20260720_02'
down_revision: Union[str, Sequence[str], None] = '20260720_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'shipping_task',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('task_type', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=True),
        sa.Column('progress', sa.JSON(), nullable=True),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_shipping_task_status_updated',
        'shipping_task',
        ['status', 'updated_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_shipping_task_status_updated', table_name='shipping_task')
    op.drop_table('shipping_task')
