"""
Pydantic schemas for TaskDueDateRequest operations.
"""

from datetime import date, datetime
from pydantic import BaseModel, Field


class DueDateRequestCreate(BaseModel):
    task_id: int
    requested_date: date
    reason: str = Field(..., min_length=1, max_length=1000)


class DueDateRequestRead(BaseModel):
    id: int
    task_id: int
    task_title: str | None = None
    requested_by_id: int
    requested_by_name: str | None = None
    manager_id: int
    manager_name: str | None = None
    requested_date: date
    reason: str
    status: str
    created_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_request(cls, req) -> "DueDateRequestRead":
        return cls(
            id=req.id,
            task_id=req.task_id,
            task_title=req.task.title if req.task else None,
            requested_by_id=req.requested_by_id,
            requested_by_name=req.requester.name if req.requester else None,
            manager_id=req.manager_id,
            manager_name=req.manager.name if req.manager else None,
            requested_date=req.requested_date,
            reason=req.reason,
            status=req.status,
            created_at=req.created_at,
            resolved_at=req.resolved_at,
        )


class DueDateRequestUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(approved|rejected)$")
