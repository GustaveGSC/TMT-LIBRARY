"""add finance customer aliases and manual mapping

Revision ID: 20260721_02
Revises: 20260721_01
Create Date: 2026-07-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20260721_02'
down_revision: Union[str, Sequence[str], None] = '20260721_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not (
        inspector.has_table('shipping_record')
        and inspector.has_table('return_record')
    ):
        return
    invalid_count = connection.execute(sa.text("""
        SELECT COUNT(*) FROM shipping_record
        WHERE source = 'finance'
          AND (ecommerce_order_no IS NULL OR product_code IS NULL OR shipped_date IS NULL)
    """)).scalar_one()
    if invalid_count:
        raise RuntimeError(
            f'发现 {invalid_count} 条财务发货记录缺少 UPSERT 键，拒绝自动规范 line_no'
        )
    duplicate_count = connection.execute(sa.text("""
        SELECT COUNT(*) FROM (
            SELECT ecommerce_order_no, product_code, shipped_date
            FROM shipping_record
            WHERE source = 'finance'
            GROUP BY ecommerce_order_no, product_code, shipped_date
            HAVING COUNT(*) > 1
        ) AS duplicate_finance_keys
    """)).scalar_one()
    if duplicate_count:
        raise RuntimeError(
            f'发现 {duplicate_count} 组重复财务发货键，拒绝自动规范 line_no；请人工核查后重试迁移'
        )

    op.add_column('shipping_record', sa.Column('customer_alias', sa.String(255), nullable=True))
    op.add_column('return_record', sa.Column('customer_alias', sa.String(255), nullable=True))
    op.create_index('ix_shipping_record_customer_alias', 'shipping_record', ['customer_alias'])
    op.create_index('ix_return_record_customer_alias', 'return_record', ['customer_alias'])
    if connection.dialect.name == 'mysql':
        line_no_expression = "CONCAT('F:', DATE_FORMAT(shipped_date, '%Y%m%d'))"
    else:
        line_no_expression = "'F:' || strftime('%Y%m%d', shipped_date)"
    connection.execute(sa.text(f"""
        UPDATE shipping_record
        SET line_no = {line_no_expression}
        WHERE source = 'finance' AND line_no IS NULL
    """))

    op.create_table(
        'shipping_finance_customer_mapping',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('customer_alias', sa.String(255), nullable=False),
        sa.Column('is_export', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('country', sa.String(100), nullable=True),
        sa.Column('brand', sa.String(100), nullable=True),
        sa.Column('note', sa.String(1000), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('customer_alias', name='uq_finance_customer_mapping_alias'),
    )


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if inspector.has_table('shipping_finance_customer_mapping'):
        op.drop_table('shipping_finance_customer_mapping')
    if inspector.has_table('return_record') and 'customer_alias' in {
        column['name'] for column in inspector.get_columns('return_record')
    }:
        op.drop_index('ix_return_record_customer_alias', table_name='return_record')
        op.drop_column('return_record', 'customer_alias')
    if inspector.has_table('shipping_record') and 'customer_alias' in {
        column['name'] for column in inspector.get_columns('shipping_record')
    }:
        op.drop_index('ix_shipping_record_customer_alias', table_name='shipping_record')
        op.drop_column('shipping_record', 'customer_alias')
