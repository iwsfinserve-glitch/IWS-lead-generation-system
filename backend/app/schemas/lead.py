"""
Pydantic schemas for LeadSource, Lead, and LeadTimeline operations.
"""

from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field

from app.models.enums import LeadStatus


# ── LeadSource Schemas ─────────────────────────────────────────────────

class LeadSourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    priority: str = Field("medium", pattern=r"^(high|medium|low)$")


class LeadSourceRead(BaseModel):
    id: int
    name: str
    priority: str
    created_at: datetime

    model_config = {"from_attributes": True}


class LeadSourceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    priority: str | None = Field(None, pattern=r"^(high|medium|low)$")


# ── Lead Schemas ───────────────────────────────────────────────────────

class LeadCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    profession: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=1, max_length=255)
    phone_number: str = Field(..., min_length=1, max_length=50)
    address: str | None = None
    dob: date | None = None
    source_id: int | None = None
    assigned_rep_id: int | None = None
    note: str | None = None


class WebLeadCreate(BaseModel):
    """Schema for the public SEO / website contact form intake endpoint.

    Does not accept source_id or assigned_rep_id — those are set server-side.
    `message` maps to the initial note/inquiry from the web form.
    """
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=1, max_length=255)
    phone_number: str = Field(..., min_length=1, max_length=50)
    profession: str = Field(..., min_length=1, max_length=255)
    address: str | None = None
    dob: date | None = None
    message: str | None = None   # The inquiry/message field from the contact form


class LeadRead(BaseModel):
    id: int
    name: str
    profession: str | None
    email: str | None
    phone_number: str | None
    address: str | None
    dob: date | None = None
    age: int | None = None
    status: LeadStatus
    last_contact: date | None
    source_id: int | None
    assigned_rep_id: int | None
    created_at: datetime
    source_name: str | None = None
    source_priority: str | None = None
    assigned_rep_name: str | None = None

    # Denormalized AI score cache — None until first AI analysis run
    ai_score: float | None = None
    ai_score_label: str | None = None          # "hot" | "warm" | "cold"
    ai_score_updated_at: datetime | None = None

    # Denormalized client classification — None until first classification run
    client_classification: str | None = None   # "hni" | "professional" | "retail"
    client_classification_updated_at: datetime | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_lead(cls, lead) -> "LeadRead":
        return cls(
            id=lead.id,
            name=lead.name,
            profession=lead.profession,
            email=lead.email,
            phone_number=lead.phone_number,
            address=lead.address,
            dob=lead.dob,
            age=lead.age,
            status=lead.status,
            last_contact=lead.last_contact,
            source_id=lead.source_id,
            assigned_rep_id=lead.assigned_rep_id,
            created_at=lead.created_at,
            source_name=lead.source.name if lead.source else None,
            source_priority=lead.source.priority if lead.source else "medium",
            assigned_rep_name=lead.assigned_rep.name if lead.assigned_rep else None,
            # AI cache columns — safe getattr in case migration hasn't run yet
            ai_score=getattr(lead, "ai_score", None),
            ai_score_label=getattr(lead, "ai_score_label", None),
            ai_score_updated_at=getattr(lead, "ai_score_updated_at", None),
            # Classification cache — safe getattr for same reason
            client_classification=getattr(lead, "client_classification", None),
            client_classification_updated_at=getattr(lead, "client_classification_updated_at", None),
        )


class LeadUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    profession: str | None = None
    email: str | None = None
    phone_number: str | None = None
    address: str | None = None
    dob: date | None = None
    status: LeadStatus | None = None
    last_contact: date | None = None
    source_id: int | None = None
    assigned_rep_id: int | None = None


# ── LeadTimeline Schemas ───────────────────────────────────────────────

class LeadTimelineCreate(BaseModel):
    """For manually adding a note/event to a lead's timeline."""
    event_type: str = Field("note_added", max_length=100)
    event_metadata: dict = Field(default_factory=dict)


class LeadTimelineRead(BaseModel):
    id: int
    lead_id: int
    user_id: int | None       # None for system-generated entries (e.g. SEO web form)
    event_type: str
    event_metadata: dict
    created_at: datetime
    user_name: str | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_timeline(cls, entry) -> "LeadTimelineRead":
        return cls(
            id=entry.id,
            lead_id=entry.lead_id,
            user_id=entry.user_id,
            event_type=entry.event_type,
            event_metadata=entry.event_metadata,
            created_at=entry.created_at,
            user_name=entry.user.name if entry.user else None,
        )
