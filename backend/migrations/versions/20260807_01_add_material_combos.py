"""add aftersale material combos

Revision ID: 20260807_01
Revises: 20260731_02
Create Date: 2026-08-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = '20260807_01'
down_revision = '20260731_02'
branch_labels = None
depends_on = None


def _material_code_type():
    # 必须与生产历史表 import_product_raw.code 的排序规则一致，保证 JOIN 可执行。
    return sa.String(255).with_variant(
        mysql.VARCHAR(255, collation='utf8mb4_0900_ai_ci'), 'mysql'
    )


def upgrade():
    op.create_table(
        'material_combo',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('remark', sa.Text(), nullable=True),
        sa.Column('is_disabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_by', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('name', name='uq_material_combo_name'),
    )
    op.create_index('ix_material_combo_disabled', 'material_combo', ['is_disabled'])
    op.create_index('ix_material_combo_category', 'material_combo', ['category'])
    op.create_table(
        'material_combo_item',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            'combo_id', sa.Integer(),
            sa.ForeignKey('material_combo.id', ondelete='CASCADE'), nullable=False,
        ),
        sa.Column('material_code', _material_code_type(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            'combo_id', 'material_code', name='uq_material_combo_item_combo_code',
        ),
    )
    op.create_index(
        'ix_material_combo_item_combo', 'material_combo_item', ['combo_id'],
    )


def downgrade():
    op.drop_index('ix_material_combo_item_combo', table_name='material_combo_item')
    op.drop_table('material_combo_item')
    op.drop_index('ix_material_combo_category', table_name='material_combo')
    op.drop_index('ix_material_combo_disabled', table_name='material_combo')
    op.drop_table('material_combo')
