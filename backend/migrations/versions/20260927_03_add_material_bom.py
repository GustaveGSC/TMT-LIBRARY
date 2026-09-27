"""add material_bom / material_bom_line (研发 BOM，单层存储)

Revision ID: 20260927_03
Revises: 20260927_02
Create Date: 2026-09-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = '20260927_03'
down_revision = '20260927_02'
branch_labels = None
depends_on = None


def _code_type():
    # 与 import_product_raw 的 code 排序规则对齐，便于 JOIN
    return sa.String(255).with_variant(
        mysql.VARCHAR(255, collation='utf8mb4_0900_ai_ci'), 'mysql'
    )


def upgrade():
    op.create_table(
        'material_bom',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('version', sa.String(length=16), nullable=False, server_default=''),
        sa.Column('erp_code', _code_type(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('spec', sa.String(length=512), nullable=True),
        sa.Column('category', sa.String(length=64), nullable=True),
        sa.Column('source_file', sa.String(length=255), nullable=True),
        sa.Column('imported_by', sa.String(length=100), nullable=True),
        sa.Column('imported_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', 'version', name='uq_material_bom_code_version'),
    )
    op.create_index('ix_material_bom_erp_code', 'material_bom', ['erp_code'], unique=False)
    op.create_table(
        'material_bom_line',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('bom_id', sa.Integer(), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('version', sa.String(length=16), nullable=False, server_default=''),
        sa.Column('erp_code', _code_type(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('spec', sa.String(length=512), nullable=True),
        sa.Column('category', sa.String(length=64), nullable=True),
        sa.Column('qty', sa.Numeric(14, 4), nullable=False, server_default='1'),
        sa.Column('unit', sa.String(length=16), nullable=True),
        sa.ForeignKeyConstraint(['bom_id'], ['material_bom.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_material_bom_line_bom_id', 'material_bom_line', ['bom_id'], unique=False)
    op.create_index('ix_material_bom_line_erp_code', 'material_bom_line', ['erp_code'], unique=False)
    op.create_index('ix_material_bom_line_code_version', 'material_bom_line', ['code', 'version'], unique=False)


def downgrade():
    op.drop_table('material_bom_line')
    op.drop_table('material_bom')
