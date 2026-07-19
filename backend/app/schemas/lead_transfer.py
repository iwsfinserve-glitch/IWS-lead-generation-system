"""
Pydantic schemas for LeadTransferRequest operations.
"""

from datetime import datetime
from pydantic import BaseModel, Field


class LeadTransferRequestCreate(BaseModel):
    lead_id: int
    to_user_id: int
    reason: str | None = Field(None, max_length=1000)


class LeadTransferRequestRead(BaseModel):
    id: int
    lead_id: int
    lead_name: str | None = None
    from_user_id: int
    from_user_name: str | None = None
    to_user_id: int
    to_user_name: str | None = None
    reason: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_request(cls, req) -> "LeadTransferRequestRead":
        return cls(
            id=req.id,
            lead_id=req.lead_id,
            lead_name=req.lead.name if req.lead else None,
            from_user_id=req.from_user_id,
            from_user_name=req.from_user.name if req.from_user else None,
            to_user_id=req.to_user_id,
            to_user_name=req.to_user.name if req.to_user else None,
            reason=req.reason,
            status=req.status,
            created_at=req.created_at,
        )


class LeadTransferRequestUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(approved|rejected)$")
