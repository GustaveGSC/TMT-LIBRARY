"""remove retired guest role

Revision ID: 20260723_01
Revises: 20260721_04
Create Date: 2026-07-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20260723_01'
down_revision: Union[str, Sequence[str], None] = '20260721_04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table('roles'):
        return
    role_id = connection.execute(
        sa.text("SELECT id FROM roles WHERE name = :name"),
        {'name': 'guest'},
    ).scalar()
    if role_id is None:
        return
    if inspector.has_table('user_roles'):
        connection.execute(
            sa.text("DELETE FROM user_roles WHERE role_id = :role_id"),
            {'role_id': role_id},
        )
    if inspector.has_table('role_permissions'):
        connection.execute(
            sa.text("DELETE FROM role_permissions WHERE role_id = :role_id"),
            {'role_id': role_id},
        )
    connection.execute(
        sa.text("DELETE FROM roles WHERE id = :role_id"),
        {'role_id': role_id},
    )


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if not inspector.has_table('roles'):
        return
    connection.execute(
        sa.text(
            "INSERT INTO roles (name, description) "
            "SELECT :name, :description WHERE NOT EXISTS ("
            "SELECT 1 FROM roles WHERE name = :name)"
        ),
        {
            'name': 'guest',
            'description': '游客（内置）——仅可查看产品库',
        },
    )
    if not inspector.has_table('permissions') or not inspector.has_table('role_permissions'):
        return
    role_id = connection.execute(
        sa.text("SELECT id FROM roles WHERE name = :name"),
        {'name': 'guest'},
    ).scalar()
    permission_id = connection.execute(
        sa.text("SELECT id FROM permissions WHERE code = :code"),
        {'code': 'product:view'},
    ).scalar()
    if role_id is not None and permission_id is not None:
        connection.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT :role_id, :permission_id WHERE NOT EXISTS ("
                "SELECT 1 FROM role_permissions "
                "WHERE role_id = :role_id AND permission_id = :permission_id)"
            ),
            {'role_id': role_id, 'permission_id': permission_id},
        )
