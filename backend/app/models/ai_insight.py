# backend/app/models/ai_insight.py
"""
LeadAIInsight — stores the structured result of every AI analysis run on a lead.

Design choices:
- One table for all insight types (score, contact_timing, future types) to avoid
  proliferation of narrow tables. insight_type discriminates; payload stores the
  full structured result as JSON.
- score / confidence are denormalized out of payload for quick DB-level filtering
  without a JSON extraction function.
- CASCADE DELETE from leads: insights are derived data, not primary records.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Use JSONB on PostgreSQL for efficient indexing; fallback to plain JSON elsewhere
_JSON = JSON().with_variant(JSONB, "postgresql")


class LeadAIInsight(Base):
    """Persisted result of an AI analysis run on a lead.

    insight_type values:
        "score"          — from LeadScoringFeature
        "contact_timing" — from ContactTimingFeature (Phase 2)
        (extensible — add new types without schema changes)
    """

    __tablename__ = "lead_ai_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    lead_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    insight_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="'score' | 'contact_timing' | future types",
    )

    payload: Mapped[dict] = mapped_column(
        _JSON,
        nullable=False,
        default=dict,
        comment="Full structured result from the AI feature (LeadScoreResult dict, etc.)",
    )

    # Denormalized from payload for DB-level sorting/filtering without JSON extraction
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    model_used: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Gemini model name used for this run (e.g. 'gemini-2.0-flash')",
    )

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ──────────────────────────────────────────────────
    lead: Mapped["Lead"] = relationship(  # noqa: F821
        "Lead", back_populates="ai_insights"
    )

    def __repr__(self) -> str:
        return (
            f"<LeadAIInsight id={self.id} lead_id={self.lead_id} "
            f"type={self.insight_type!r} score={self.score}>"
        )
