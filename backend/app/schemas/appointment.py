"""
Pydantic schemas for Appointment operations.
"""

from datetime import datetime
from pydantic import BaseModel, Field, model_validator

from app.models.enums import AppointmentMode


class AppointmentCreate(BaseModel):
    lead_id: int
    title: str = Field(..., min_length=1, max_length=500)
    note: str | None = None
    mode: AppointmentMode = AppointmentMode.online
    location: str | None = None
    start_time: datetime
    end_time: datetime

    @model_validator(mode="after")
    def validate_times(self) -> "AppointmentCreate":
        if self.start_time >= self.end_time:
            raise ValueError("end_time must be after start_time")
        return self


class AppointmentRead(BaseModel):
    id: int
    lead_id: int
    user_id: int
    title: str
    note: str | None
    mode: AppointmentMode
    location: str | None
    start_time: datetime
    end_time: datetime
    google_event_id: str | None
    last_synced_at: datetime | None
    lead_name: str | None = None
    user_name: str | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_appointment(cls, appt) -> "AppointmentRead":
        return cls(
            id=appt.id,
            lead_id=appt.lead_id,
            user_id=appt.user_id,
            title=appt.title,
            note=appt.note,
            mode=appt.mode,
            location=appt.location,
            start_time=appt.start_time,
            end_time=appt.end_time,
            google_event_id=appt.google_event_id,
            last_synced_at=appt.last_synced_at,
            lead_name=appt.lead.name if appt.lead else None,
            user_name=appt.user.name if appt.user else None,
        )


class AppointmentUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=500)
    note: str | None = None
    mode: AppointmentMode | None = None
    location: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
