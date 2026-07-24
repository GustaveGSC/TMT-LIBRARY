"""add database-backed shipping task lease

Revision ID: 20260724_01
Revises: 20260723_02
Create Date: 2026-07-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20260724_01'
down_revision: Union[str, Sequence[str], None] = '20260723_02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('shipping_task') as batch_op:
        batch_op.add_column(sa.Column('lease_key', sa.String(length=64), nullable=True))
        batch_op.create_unique_constraint(
            'uq_shipping_task_lease_key',
            ['lease_key'],
        )


def downgrade() -> None:
    with op.batch_alter_table('shipping_task') as batch_op:
        batch_op.drop_constraint('uq_shipping_task_lease_key', type_='unique')
        batch_op.drop_column('lease_key')
