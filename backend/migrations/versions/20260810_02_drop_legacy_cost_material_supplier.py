"""drop the empty legacy cost material supplier table

Revision ID: 20260810_02
Revises: 20260810_01
Create Date: 2026-08-11

Downgrade restores only the legacy table structure. It cannot restore rows that
existed before upgrade; production deployment must therefore verify the table is
still empty before applying this migration.
"""
from alembic import op
import sqlalchemy as sa


revision = '20260810_02'
down_revision = '20260810_01'
branch_labels = None
depends_on = None


def upgrade():
    if 'cost_material_supplier' in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table('cost_material_supplier')


def downgrade():
    if 'cost_material_supplier' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        'cost_material_supplier',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('node_id', sa.Integer(), nullable=False),
        sa.Column('supplier_name', sa.String(64), nullable=False),
        sa.Column('unit_price', sa.Numeric(12, 4), nullable=False),
        sa.Column('price_date', sa.Date(), nullable=True),
        sa.Column('is_preferred', sa.Boolean(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['node_id'], ['cost_bom_node.id'],
            name='cost_material_supplier_ibfk_1', ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index(
        'ix_cost_material_supplier_node_id',
        'cost_material_supplier', ['node_id'], unique=False,
    )
