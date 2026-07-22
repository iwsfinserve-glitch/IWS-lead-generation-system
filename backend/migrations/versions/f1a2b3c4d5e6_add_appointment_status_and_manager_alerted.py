"""add_appointment_status_and_manager_alerted

Revision ID: f1a2b3c4d5e6
Revises: e7f1a2b3c4d5
Create Date: 2026-07-20 11:00:00.000000

Adds:
    - appointments.status          VARCHAR(50) DEFAULT 'upcoming' NOT NULL
    - appointments.manager_alerted BOOLEAN     DEFAULT false      NOT NULL
    - Composite index on (status, end_time) for the reconcile query
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e7f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="upcoming",
        ),
    )
    op.add_column(
        "appointments",
        sa.Column(
            "manager_alerted",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.create_index(
        "ix_appointments_status_end_time",
        "appointments",
        ["status", "end_time"],
    )


def downgrade() -> None:
    op.drop_index("ix_appointments_status_end_time", table_name="appointments")
    op.drop_column("appointments", "manager_alerted")
    op.drop_column("appointments", "status")
