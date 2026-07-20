"""Production schema baseline; intentionally contains no DDL.

Revision ID: 20260720_01
Revises:
Create Date: 2026-07-20
"""
from typing import Sequence, Union


revision: str = '20260720_01'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Mark the already-existing production schema as the migration baseline."""
    pass


def downgrade() -> None:
    """The baseline owns no schema objects, so downgrade is intentionally empty."""
    pass
