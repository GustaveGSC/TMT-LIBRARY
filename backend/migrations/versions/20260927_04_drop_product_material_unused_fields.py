"""drop product_material.short_name/category/spec (unused)

物料卡片的简称/分类/规格没有任何下游使用：生产上简称 0 条、分类 1 条、
规格全部与 ERP 规格相同。名称/规格一律以 ERP（import_product_raw）为准。
用户 2026-09-27 要求直接删列。

Revision ID: 20260927_04
Revises: 20260927_03
Create Date: 2026-09-27
"""

from alembic import op
import sqlalchemy as sa


revision = '20260927_04'
down_revision = '20260927_03'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('product_material') as batch:
        batch.drop_column('short_name')
        batch.drop_column('category')
        batch.drop_column('spec')


def downgrade():
    # 只恢复列结构，删掉的数据不回填
    with op.batch_alter_table('product_material') as batch:
        batch.add_column(sa.Column('short_name', sa.String(255), nullable=True))
        batch.add_column(sa.Column('category', sa.String(100), nullable=True))
        batch.add_column(sa.Column('spec', sa.String(512), nullable=True))
