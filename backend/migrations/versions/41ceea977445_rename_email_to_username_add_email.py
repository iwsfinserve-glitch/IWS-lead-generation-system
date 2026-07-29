"""rename_email_to_username_add_email

Revision ID: 41ceea977445
Revises: 0fcc86445fe6
Create Date: 2026-07-29 21:21:27.207830

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.

revision: str = '41ceea977445'
down_revision: Union[str, None] = '0fcc86445fe6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('users', 'email', new_column_name='username')
    op.drop_index('ix_users_email', table_name='users', if_exists=True)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.add_column('users', sa.Column('email', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'email')
    op.alter_column('users', 'username', new_column_name='email')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.create_index('ix_users_email', 'users', ['email'], unique=True)