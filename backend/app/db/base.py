"""
SQLAlchemy Declarative Base and central model re-exports.

Re-exports Base and all ORM models for convenient imports and Alembic migrations.
"""

from app.db.base_class import Base
from app.models.user import User
from app.models.lead import LeadSource, Lead
from app.models.interaction import (
    LeadTimeline,
    Appointment,
    Task,
    TaskDueDateRequest,
    Notification,
    LeadTransferRequest,
    LeadUpdateRequest,
)
from app.models.ai_insight import LeadAIInsight
from app.models.whatsapp_message import WhatsAppMessage, MessageDirection, MessageStatus

__all__ = [
    "Base",
    "User",
    "LeadSource",
    "Lead",
    "LeadTimeline",
    "Appointment",
    "Task",
    "TaskDueDateRequest",
    "Notification",
    "LeadTransferRequest",
    "LeadUpdateRequest",
    "LeadAIInsight",
    "WhatsAppMessage",
    "MessageDirection",
    "MessageStatus",
]
