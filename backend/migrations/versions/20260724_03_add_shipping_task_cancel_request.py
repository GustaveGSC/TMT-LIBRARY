"""add shipping task cancel request

Revision ID: 20260724_03
Revises: 20260724_02
Create Date: 2026-07-24
"""

from alembic import op
import sqlalchemy as sa


revision = '20260724_03'
down_revision = '20260724_02'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('shipping_task') as batch_op:
        batch_op.add_column(
            sa.Column('cancel_requested_at', sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column('cancel_requested_by', sa.Integer(), nullable=True)
        )


def downgrade():
    with op.batch_alter_table('shipping_task') as batch_op:
        batch_op.drop_column('cancel_requested_by')
        batch_op.drop_column('cancel_requested_at')
