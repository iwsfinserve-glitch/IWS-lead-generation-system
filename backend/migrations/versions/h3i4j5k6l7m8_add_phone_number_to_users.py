"""add_phone_number_to_users

Revision ID: h3i4j5k6l7m8
Revises: g2h3i4j5k6l7
Create Date: 2026-07-21 15:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'h3i4j5k6l7m8'
down_revision: Union[str, None] = 'g2h3i4j5k6l7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add phone_number as nullable first to avoid error on existing rows
    op.add_column('users', sa.Column('phone_number', sa.String(length=50), nullable=True))
    
    # 2. Backfill existing user rows with a default phone number
    op.execute("UPDATE users SET phone_number = '+91 00000 00000' WHERE phone_number IS NULL")
    
    # 3. Alter column to NOT NULL
    op.alter_column(
        'users',
        'phone_number',
        existing_type=sa.String(length=50),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column('users', 'phone_number')
