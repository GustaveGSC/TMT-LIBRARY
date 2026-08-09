"""add material supplier master data

Revision ID: 20260810_01
Revises: 20260807_01
Create Date: 2026-08-10
"""
from alembic import op
import sqlalchemy as sa

revision = '20260810_01'
down_revision = '20260807_01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'material_supplier',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('contact', sa.String(64), nullable=True),
        sa.Column('remark', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('name', name='uq_material_supplier_name'),
    )
    if 'cost_material_price' not in sa.inspect(op.get_bind()).get_table_names():
        return
    with op.batch_alter_table('cost_material_price') as batch:
        batch.add_column(sa.Column('supplier_id', sa.Integer(), nullable=True))
        batch.create_index('ix_cost_material_price_supplier_id', ['supplier_id'])
        batch.create_foreign_key(
            'fk_cost_material_price_supplier', 'material_supplier',
            ['supplier_id'], ['id'], ondelete='SET NULL',
        )
    op.execute(sa.text(
        "INSERT INTO material_supplier (name, created_at, updated_at) "
        "SELECT DISTINCT supplier_name, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
        "FROM cost_material_price WHERE supplier_name IS NOT NULL AND supplier_name <> ''"
    ))
    op.execute(sa.text(
        "UPDATE cost_material_price SET supplier_id = "
        "(SELECT id FROM material_supplier WHERE material_supplier.name = cost_material_price.supplier_name) "
        "WHERE supplier_name IS NOT NULL AND supplier_name <> ''"
    ))


def downgrade():
    if 'cost_material_price' in sa.inspect(op.get_bind()).get_table_names():
        with op.batch_alter_table('cost_material_price') as batch:
            batch.drop_constraint('fk_cost_material_price_supplier', type_='foreignkey')
            batch.drop_index('ix_cost_material_price_supplier_id')
            batch.drop_column('supplier_id')
    op.drop_table('material_supplier')
