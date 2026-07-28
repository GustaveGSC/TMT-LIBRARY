"""add independent product detail packages

Revision ID: 20260728_02
Revises: 20260728_01
Create Date: 2026-07-28
"""

from alembic import op
import sqlalchemy as sa


revision = '20260728_02'
down_revision = '20260728_01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'product_detail_package',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('tag_condition', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_table(
        'product_detail_package_media',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('package_id', sa.Integer(), sa.ForeignKey('product_detail_package.id', ondelete='CASCADE'), nullable=False),
        sa.Column('file_type', sa.String(20), nullable=False),
        sa.Column('original_filename', sa.String(300), nullable=False),
        sa.Column('oss_url', sa.String(1000), nullable=False),
        sa.Column('storage_key', sa.String(500), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('storage_key', name='uq_product_detail_package_media_storage_key'),
    )
    op.create_index('ix_product_detail_package_media_package_id', 'product_detail_package_media', ['package_id'])
    op.create_table(
        'product_detail_package_tag',
        sa.Column('package_id', sa.Integer(), sa.ForeignKey('product_detail_package.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('tag_id', sa.Integer(), sa.ForeignKey('product_tag.id', ondelete='CASCADE'), primary_key=True),
    )
    op.create_table(
        'product_detail_package_model',
        sa.Column('package_id', sa.Integer(), sa.ForeignKey('product_detail_package.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('model_id', sa.Integer(), sa.ForeignKey('product_model.id', ondelete='CASCADE'), primary_key=True),
    )
    op.create_table(
        'product_detail_package_cleanup_failure',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('package_id', sa.Integer(), nullable=True),
        sa.Column('storage_key', sa.String(500), nullable=False),
        sa.Column('error_message', sa.String(1000), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index(
        'ix_product_detail_package_cleanup_failure_created_at',
        'product_detail_package_cleanup_failure', ['created_at'],
    )


def downgrade():
    op.drop_index('ix_product_detail_package_cleanup_failure_created_at', table_name='product_detail_package_cleanup_failure')
    op.drop_table('product_detail_package_cleanup_failure')
    op.drop_table('product_detail_package_model')
    op.drop_table('product_detail_package_tag')
    op.drop_table('product_detail_package_media')
    op.drop_table('product_detail_package')
