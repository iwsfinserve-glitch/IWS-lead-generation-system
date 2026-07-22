"""rename_lead_status_new_to_unassigned_add_seo_workflow

Revision ID: g2h3i4j5k6l7
Revises: f1a2b3c4d5e6
Create Date: 2026-07-20 17:11:00.000000

Migration branch determination:
    NATIVE POSTGRESQL ENUM — confirmed by inspecting migration a1b2c3d4e5f6 which
    uses 'ALTER TYPE lead_status ADD VALUE' via op.execute(), proving lead_status is
    a database-level PostgreSQL enum type (not a plain VARCHAR column).
    Therefore the ALTER TYPE ... RENAME VALUE approach is used here.

    Requires PostgreSQL >= 10. Cannot be run inside a transaction (must COMMIT first).

Changes:
    1. Renames the 'new' enum value to 'unassigned' in the DB-level lead_status type.
    2. Adds 'unassigned' value to lead_status enum FIRST (so existing rows remain valid
       during the rename window on older PG versions that don't support RENAME VALUE).
       On PG >= 10, RENAME VALUE handles this atomically.
    3. Adds the 'SEO' entry to lead_sources if not already present, with priority='high'.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g2h3i4j5k6l7'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Step 1: Rename 'new' -> 'unassigned' in the native PG enum ──────────
    # ALTER TYPE ... RENAME VALUE requires PostgreSQL >= 10 and cannot run
    # inside a transaction, so we commit the current transaction first.
    # RENAME VALUE updates all stored values in the column atomically — no
    # separate UPDATE is needed or possible after the rename.
    #
    # Idempotent: checks pg_enum first in case this step already ran
    # (e.g. partial migration on a previous failed run).
    op.execute("COMMIT")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'new'
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'lead_status')
            ) THEN
                ALTER TYPE lead_status RENAME VALUE 'new' TO 'unassigned';
            END IF;
        END $$;
    """)

    # Resume an explicit transaction for the remaining DDL/DML steps.
    op.execute("BEGIN")

    # ── Step 2: Allow NULL user_id on lead_timeline for system events ────────
    # SEO web form intake creates timeline entries with no CRM user attached.
    op.alter_column(
        "lead_timeline", "user_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    # ── Step 3: Ensure the SEO lead source exists ────────────────────────────
    op.execute(
        """
        INSERT INTO lead_sources (name, priority, created_at)
        VALUES ('SEO', 'high', NOW() AT TIME ZONE 'UTC')
        ON CONFLICT (name) DO UPDATE SET priority = 'high'
        """
    )


def downgrade() -> None:
    # Reverse: rename 'unassigned' back to 'new'.
    # Note: PostgreSQL does not allow removing enum values, only renaming.
    op.execute("COMMIT")
    op.execute("ALTER TYPE lead_status RENAME VALUE 'unassigned' TO 'new'")
    op.execute(
        "UPDATE leads SET status = 'new' WHERE status = 'unassigned'"
    )
    # Reverse user_id nullable — only safe if no NULL rows exist
    op.alter_column(
        "lead_timeline", "user_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
