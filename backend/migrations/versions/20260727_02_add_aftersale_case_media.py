"""add aftersale media upload tables

Revision ID: 20260727_02
Revises: 20260727_01
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa


revision = '20260727_02'
down_revision = '20260727_01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'aftersale_case_media',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('order_no', sa.String(100), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('file_type', sa.String(20), nullable=False),
        sa.Column('original_filename', sa.String(300), nullable=False),
        sa.Column('stored_filename', sa.String(300), nullable=False),
        sa.Column('oss_url', sa.String(1000), nullable=False),
        sa.Column('storage_key', sa.String(500), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('uploaded_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('storage_key', name='uq_aftersale_case_media_storage_key'),
        sa.UniqueConstraint('order_no', 'seq', name='uq_aftersale_case_media_order_seq'),
    )
    op.create_index('ix_aftersale_case_media_order_no', 'aftersale_case_media', ['order_no'])
    op.create_table(
        'aftersale_media_upload_session',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('session_token', sa.String(128), nullable=False),
        sa.Column('order_no', sa.String(100), nullable=False),
        sa.Column('mode', sa.String(16), nullable=False),
        sa.Column('start_seq', sa.Integer(), nullable=False),
        sa.Column('reserved_start', sa.Integer(), nullable=True),
        sa.Column('end_seq', sa.Integer(), nullable=False),
        sa.Column('manifest', sa.JSON(), nullable=False),
        sa.Column('uploaded_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('session_token', name='uq_aftersale_media_session_token'),
        sa.UniqueConstraint('order_no', 'reserved_start', name='uq_aftersale_media_session_start_seq'),
    )
    op.create_index('ix_aftersale_media_session_expiry', 'aftersale_media_upload_session', ['expires_at'])
    op.create_table(
        'aftersale_media_cleanup_failure',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('storage_key', sa.String(500), nullable=False),
        sa.Column('order_no', sa.String(100), nullable=False),
        sa.Column('error_message', sa.String(1000), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_aftersale_media_cleanup_failure_storage_key', 'aftersale_media_cleanup_failure', ['storage_key'])
    op.create_index('ix_aftersale_media_cleanup_failure_order_no', 'aftersale_media_cleanup_failure', ['order_no'])


def downgrade():
    op.drop_table('aftersale_media_cleanup_failure')
    op.drop_table('aftersale_media_upload_session')
    op.drop_table('aftersale_case_media')
