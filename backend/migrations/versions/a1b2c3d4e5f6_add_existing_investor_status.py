"""Add existing_investor to lead_status enum

Revision ID: a1b2c3d4e5f6
Revises: 17ed4f6bf65f
Create Date: 2026-07-07 11:50:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '17ed4f6bf65f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL enum types are database-level objects.
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction,
    # so we commit the current transaction first.
    op.execute("COMMIT")
    op.execute("ALTER TYPE lead_status ADD VALUE IF NOT EXISTS 'existing_investor'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    # This is intentionally a no-op.
    pass
