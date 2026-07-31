"""add material library

Revision ID: 20260731_01
Revises: 20260729_01
Create Date: 2026-07-31
"""

from alembic import op
import sqlalchemy as sa


revision = '20260731_01'
down_revision = '20260729_01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'erp_group_category',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('group_code', sa.String(64), nullable=False),
        sa.Column('is_finished', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_packaged', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_semi', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_material', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_useless', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('remark', sa.String(255), nullable=True),
        sa.Column('updated_by', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('group_code', name='uq_erp_group_category_group_code'),
    )
    op.create_table(
        'product_material',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('code', sa.String(255), nullable=False),
        sa.Column('short_name', sa.String(255), nullable=True),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('spec', sa.String(512), nullable=True),
        sa.Column('cover_image', sa.String(500), nullable=True),
        sa.Column('cover_image_original', sa.String(500), nullable=True),
        sa.Column('img_updated_at', sa.Integer(), nullable=True),
        sa.Column('remark', sa.Text(), nullable=True),
        sa.Column('is_disabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('code', name='uq_product_material_code'),
    )
    op.create_index('ix_product_material_is_disabled', 'product_material', ['is_disabled'])
    if 'import_product_raw' in sa.inspect(op.get_bind()).get_table_names():
        op.add_column('import_product_raw', sa.Column('spec', sa.String(512), nullable=True))


def downgrade():
    if 'import_product_raw' in sa.inspect(op.get_bind()).get_table_names():
        op.drop_column('import_product_raw', 'spec')
    op.drop_index('ix_product_material_is_disabled', table_name='product_material')
    op.drop_table('product_material')
    op.drop_table('erp_group_category')
