"""
Pydantic schemas for LeadSource, Lead, and LeadTimeline operations.
"""

from datetime import date, datetime
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
    profession: str | None = None
    email: str | None = None
    phone_number: str | None = None
    address: str | None = None
    source_id: int | None = None
    assigned_rep_id: int | None = None


class LeadRead(BaseModel):
    id: int
    name: str
    profession: str | None
    email: str | None
    phone_number: str | None
    address: str | None
    status: LeadStatus
    last_contact: date | None
    source_id: int | None
    assigned_rep_id: int | None
    created_at: datetime
    source_name: str | None = None
    assigned_rep_name: str | None = None

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
            status=lead.status,
            last_contact=lead.last_contact,
            source_id=lead.source_id,
            assigned_rep_id=lead.assigned_rep_id,
            created_at=lead.created_at,
            source_name=lead.source.name if lead.source else None,
            assigned_rep_name=lead.assigned_rep.name if lead.assigned_rep else None,
        )


class LeadUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    profession: str | None = None
    email: str | None = None
    phone_number: str | None = None
    address: str | None = None
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
    user_id: int
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
