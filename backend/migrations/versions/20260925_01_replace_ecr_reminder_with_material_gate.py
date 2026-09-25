"""replace ecr reminder with material gate

Revision ID: 20260925_01
Revises: 20260904_02
Create Date: 2026-09-25
"""

from alembic import op
import sqlalchemy as sa


revision = '20260925_01'
down_revision = '20260904_02'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'material_gate',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('level', sa.String(length=16), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_material_gate_code', 'material_gate', ['code'], unique=False)

    # 旧提醒是无物料编码的自由文本，无法可靠迁移为门禁，按产品决策直接丢弃。
    if sa.inspect(op.get_bind()).has_table('ecr_reminder'):
        op.drop_table('ecr_reminder')


def downgrade():
    op.create_table(
        'ecr_reminder',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('content', sa.String(length=500), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.drop_index('ix_material_gate_code', table_name='material_gate')
    op.drop_table('material_gate')
