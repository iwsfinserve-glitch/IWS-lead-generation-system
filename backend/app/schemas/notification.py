"""
Pydantic schemas for Notification operations.
"""

from datetime import datetime
from pydantic import BaseModel


class NotificationRead(BaseModel):
    id: int
    user_id: int
    message: str
    title: str | None = None
    notification_type: str | None = None
    is_read: bool
    link_type: str | None = None
    link_id: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UnreadCountResponse(BaseModel):
    count: int
