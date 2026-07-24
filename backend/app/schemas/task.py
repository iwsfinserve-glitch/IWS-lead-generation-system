"""
Pydantic schemas for Task operations.
"""

from datetime import date, datetime, timezone
from pydantic import BaseModel, Field, field_validator


class TaskCreate(BaseModel):
    user_id: int
    title: str = Field(..., min_length=1, max_length=500)
    notes: str | None = None
    due: date | None = None
    end_time: datetime | None = None

    @field_validator("end_time")
    @classmethod
    def validate_end_time(cls, v: datetime | None) -> datetime | None:
        if v and v < datetime.now(timezone.utc):
            raise ValueError("end_time cannot be in the past")
        return v


class TaskRead(BaseModel):
    id: int
    user_id: int
    assigned_by: int | None
    title: str
    notes: str | None
    status: str
    assigned_on: datetime
    due: date | None
    end_time: datetime | None = None
    end_time_notified: bool = False
    completed_at: datetime | None
    google_task_id: str | None
    last_synced_at: datetime | None
    user_name: str | None = None
    assigned_by_name: str | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_task(cls, task) -> "TaskRead":
        return cls(
            id=task.id,
            user_id=task.user_id,
            assigned_by=task.assigned_by,
            title=task.title,
            notes=task.notes,
            status=task.status,
            assigned_on=task.assigned_on,
            due=task.due,
            end_time=task.end_time,
            end_time_notified=task.end_time_notified,
            completed_at=task.completed_at,
            google_task_id=task.google_task_id,
            last_synced_at=task.last_synced_at,
            user_name=task.user.name if task.user else None,
            assigned_by_name=task.assigner.name if task.assigner else None,
        )


class TaskUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=500)
    notes: str | None = None
    status: str | None = Field(None, pattern=r"^(needsAction|completed)$")
    due: date | None = None
    end_time: datetime | None = None

    @field_validator("end_time")
    @classmethod
    def validate_end_time(cls, v: datetime | None) -> datetime | None:
        if v and v < datetime.now(timezone.utc):
            raise ValueError("end_time cannot be in the past")
        return v


class TaskSelfCreate(BaseModel):
    """Schema for reps creating tasks assigned to themselves."""
    title: str = Field(..., min_length=1, max_length=500)
    notes: str | None = None
    due: date | None = None
    end_time: datetime | None = None

    @field_validator("end_time")
    @classmethod
    def validate_end_time(cls, v: datetime | None) -> datetime | None:
        if v and v < datetime.now(timezone.utc):
            raise ValueError("end_time cannot be in the past")
        return v
