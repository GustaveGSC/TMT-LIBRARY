"""add name column to material gate

Revision ID: 20260926_01
Revises: 20260925_01
Create Date: 2026-09-26
"""

from alembic import op
import sqlalchemy as sa


revision = '20260926_01'
down_revision = '20260925_01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'material_gate',
        sa.Column('name', sa.String(length=200), nullable=False, server_default=''),
    )


def downgrade():
    op.drop_column('material_gate', 'name')
