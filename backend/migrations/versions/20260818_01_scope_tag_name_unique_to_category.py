"""scope product_tag.name uniqueness to (category_id, name)

Revision ID: 20260818_01
Revises: 20260810_02
Create Date: 2026-08-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '20260818_01'
down_revision = '20260810_02'
branch_labels = None
depends_on = None

NEW_INDEX_NAME = 'uq_product_tag_category_name'


def upgrade():
    bind = op.get_bind()
    if 'product_tag' not in set(inspect(bind).get_table_names()):
        return
    inspector = inspect(bind)
    # MySQL 的 unique index 和 unique constraint 是同一份元数据，get_indexes 和
    # get_unique_constraints 会重复报告同一个索引，只能按其中一种方式 drop 一次，否则第二次 drop 报错
    dropped_names = set()
    with op.batch_alter_table('product_tag') as batch_op:
        for idx in inspector.get_indexes('product_tag'):
            if idx.get('unique') and idx.get('column_names') == ['name']:
                batch_op.drop_index(idx['name'])
                dropped_names.add(idx['name'])
        for uc in inspector.get_unique_constraints('product_tag'):
            if uc.get('column_names') == ['name'] and uc['name'] not in dropped_names:
                batch_op.drop_constraint(uc['name'], type_='unique')
        batch_op.create_index(NEW_INDEX_NAME, ['category_id', 'name'], unique=True)


def downgrade():
    bind = op.get_bind()
    if 'product_tag' not in set(inspect(bind).get_table_names()):
        return
    inspector = inspect(bind)
    with op.batch_alter_table('product_tag') as batch_op:
        existing = {idx['name'] for idx in inspector.get_indexes('product_tag')}
        if NEW_INDEX_NAME in existing:
            batch_op.drop_index(NEW_INDEX_NAME)
        batch_op.create_unique_constraint('name', ['name'])
