"""add_ai_insights_and_lead_ai_columns

Revision ID: e7f1a2b3c4d5
Revises: dc6d67a82907
Create Date: 2026-07-13 11:30:00.000000

Creates:
    - lead_ai_insights table  (AI analysis history per lead)
    - leads.ai_score          (denormalized for list sorting)
    - leads.ai_score_label    (hot / warm / cold)
    - leads.ai_score_updated_at
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e7f1a2b3c4d5"
down_revision: Union[str, None] = "dc6d67a82907"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Create lead_ai_insights table ────────────────────────────────
    op.create_table(
        "lead_ai_insights",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "lead_id",
            sa.Integer(),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("insight_type", sa.String(length=50), nullable=False),
        # Use JSONB on PostgreSQL for efficient indexing; plain JSON on SQLite (tests)
        sa.Column(
            "payload",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("model_used", sa.String(length=100), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_lead_ai_insights_lead_id",
        "lead_ai_insights",
        ["lead_id"],
    )

    # ── 2. Add denormalized AI columns to leads ──────────────────────────
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS ai_score DOUBLE PRECISION;")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS ai_score_label VARCHAR(10);")
    op.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS ai_score_updated_at TIMESTAMPTZ;")


def downgrade() -> None:
    # Remove denormalized columns from leads
    op.drop_column("leads", "ai_score_updated_at")
    op.drop_column("leads", "ai_score_label")
    op.drop_column("leads", "ai_score")

    # Drop lead_ai_insights table
    op.drop_index("ix_lead_ai_insights_lead_id", table_name="lead_ai_insights")
    op.drop_table("lead_ai_insights")
