"""add material_image table (multiple images per material)

Revision ID: 20260927_02
Revises: 20260927_01
Create Date: 2026-09-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = '20260927_02'
down_revision = '20260927_01'
branch_labels = None
depends_on = None


def _code_type():
    # 与 import_product_raw / product_material 的 code 排序规则对齐，便于 JOIN
    return sa.String(255).with_variant(
        mysql.VARCHAR(255, collation='utf8mb4_0900_ai_ci'), 'mysql'
    )


def upgrade():
    op.create_table(
        'material_image',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', _code_type(), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('orig_url', sa.String(length=500), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_by', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_material_image_code', 'material_image', ['code'], unique=False)

    # 历史单图搬进新表作为第一张；product_material 旧三列保留不删，便于回退
    op.execute(
        "INSERT INTO material_image (code, url, orig_url, sort_order, created_by, created_at, updated_at) "
        "SELECT code, cover_image, cover_image_original, 0, 'migration', "
        "COALESCE(updated_at, created_at), COALESCE(updated_at, created_at) "
        "FROM product_material WHERE cover_image IS NOT NULL AND cover_image <> ''"
    )


def downgrade():
    op.drop_index('ix_material_image_code', table_name='material_image')
    op.drop_table('material_image')
