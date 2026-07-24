"""
Lead & LeadSource Models — the core CRM entities.

LeadSource — categorises how a lead was acquired (e.g. Walk-in, SEO).
Lead       — an individual prospect tracked through the sales pipeline.

Status lifecycle:
    unassigned → in_progress → potential → converted_to_investor → existing_investor (monthly rollover)
                             ↘ non_potential
"""

from datetime import date, datetime, timezone

from sqlalchemy import (
    Integer, String, Enum, Date, DateTime, ForeignKey, Text, Float,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import LeadStatus





class LeadSource(Base):
    """How a lead was acquired (e.g. 'Walk-in', 'SEO', 'Referral')."""

    __tablename__ = "lead_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    priority: Mapped[str] = mapped_column(
        String(50), nullable=False, default="medium",
        comment="high | medium | low",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relationships ──
    leads: Mapped[list["Lead"]] = relationship("Lead", back_populates="source", lazy="selectin")

    def __repr__(self) -> str:
        return f"<LeadSource id={self.id} name={self.name!r}>"







class Lead(Base):
    """An individual prospect in the sales pipeline."""

    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    profession: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)

    @property
    def age(self) -> int | None:
        """Calculate age from DOB."""
        if not self.dob:
            return None
        today = date.today()
        return today.year - self.dob.year - ((today.month, today.day) < (self.dob.month, self.dob.day))

    status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus, name="lead_status", create_constraint=True),
        nullable=False,
        default=LeadStatus.unassigned,
    )
    last_contact: Mapped[date | None] = mapped_column(Date, nullable=True)

    source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("lead_sources.id"), nullable=True,
    )
    assigned_rep_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────
    source: Mapped["LeadSource | None"] = relationship(
        "LeadSource", back_populates="leads", lazy="selectin",
    )
    assigned_rep: Mapped["User | None"] = relationship(               # noqa: F821
        "User", back_populates="leads", lazy="selectin",
    )
    timeline: Mapped[list["LeadTimeline"]] = relationship(            # noqa: F821
        "LeadTimeline", back_populates="lead",
        cascade="all, delete-orphan", lazy="select",
    )
    appointments: Mapped[list["Appointment"]] = relationship(         # noqa: F821
        "Appointment", back_populates="lead",
        cascade="all, delete-orphan", lazy="select",
    )

    # ── Denormalized AI score cache (updated by POST /leads/{id}/ai/score) ──
    # Stored directly on Lead so list views can sort/filter without a join.
    ai_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_score_label: Mapped[str | None] = mapped_column(
        String(10), nullable=True,
        comment="'hot' | 'warm' | 'cold' — mirrors latest LeadAIInsight.payload.label",
    )
    ai_score_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # ── Denormalized client-classification cache (updated by the classification AI feature) ──
    # Stored directly on Lead so list/card views can display the badge without
    # an extra JOIN against lead_ai_insights on every page load.
    client_classification: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
        comment="'hni' | 'professional' | 'retail' | NULL (unclassified)",
    )
    client_classification_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    ai_insights: Mapped[list["LeadAIInsight"]] = relationship(         # noqa: F821
        "LeadAIInsight", back_populates="lead",
        cascade="all, delete-orphan", lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Lead id={self.id} name={self.name!r} status={self.status.value}>"
