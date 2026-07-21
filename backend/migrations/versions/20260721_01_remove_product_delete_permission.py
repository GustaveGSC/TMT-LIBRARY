"""remove unsupported product delete permission

Revision ID: 20260721_01
Revises: 20260720_02
Create Date: 2026-07-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20260721_01'
down_revision: Union[str, Sequence[str], None] = '20260720_02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    if not sa.inspect(connection).has_table('permissions'):
        return
    permission_id = connection.execute(
        sa.text("SELECT id FROM permissions WHERE code = :code"),
        {'code': 'product:delete'},
    ).scalar()
    if permission_id is None:
        return
    connection.execute(
        sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"),
        {'permission_id': permission_id},
    )
    connection.execute(
        sa.text("DELETE FROM permissions WHERE id = :permission_id"),
        {'permission_id': permission_id},
    )


def downgrade() -> None:
    connection = op.get_bind()
    if not sa.inspect(connection).has_table('permissions'):
        return
    connection.execute(
        sa.text(
            "INSERT INTO permissions (code, name, description) "
            "SELECT :code, :name, :description WHERE NOT EXISTS ("
            "SELECT 1 FROM permissions WHERE code = :code)"
        ),
        {
            'code': 'product:delete',
            'name': '删除产品记录',
            'description': '删除产品记录',
        },
    )
