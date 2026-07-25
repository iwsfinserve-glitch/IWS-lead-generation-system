"""
Pydantic schemas for LeadUpdateRequest operations.
"""

from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field


class LeadUpdateRequestCreate(BaseModel):
    lead_id: int
    # At least one proposed_* field must be non-null (enforced in the route)
    proposed_email: str | None = Field(None, max_length=255)
    proposed_phone: str | None = Field(None, max_length=50)
    proposed_address: str | None = None
    proposed_dob: date | None = None
    proposed_source_id: int | None = None
    reason: str = Field(..., min_length=1, max_length=1000)


class LeadUpdateRequestRead(BaseModel):
    id: int
    lead_id: int
    lead_name: str | None = None
    requested_by_id: int
    requested_by_name: str | None = None
    manager_id: int
    manager_name: str | None = None

    proposed_email: str | None
    proposed_phone: str | None
    proposed_address: str | None
    proposed_dob: date | None
    proposed_source_id: int | None
    proposed_source_name: str | None = None

    current_email: str | None
    current_phone: str | None
    current_address: str | None
    current_dob: date | None
    current_source_id: int | None
    current_source_name: str | None = None

    reason: str
    status: str
    created_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_request(cls, req) -> "LeadUpdateRequestRead":
        # Resolve source names via lead's source relationship or direct source FK
        proposed_src_name = None
        current_src_name = None
        if req.lead:
            if req.lead.source:
                current_src_name = req.lead.source.name
        return cls(
            id=req.id,
            lead_id=req.lead_id,
            lead_name=req.lead.name if req.lead else None,
            requested_by_id=req.requested_by_id,
            requested_by_name=req.requester.name if req.requester else None,
            manager_id=req.manager_id,
            manager_name=req.manager.name if req.manager else None,
            proposed_email=req.proposed_email,
            proposed_phone=req.proposed_phone,
            proposed_address=req.proposed_address,
            proposed_dob=req.proposed_dob,
            proposed_source_id=req.proposed_source_id,
            proposed_source_name=proposed_src_name,
            current_email=req.current_email,
            current_phone=req.current_phone,
            current_address=req.current_address,
            current_dob=req.current_dob,
            current_source_id=req.current_source_id,
            current_source_name=current_src_name,
            reason=req.reason,
            status=req.status,
            created_at=req.created_at,
            resolved_at=req.resolved_at,
        )


class LeadUpdateRequestUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(approved|rejected)$")
