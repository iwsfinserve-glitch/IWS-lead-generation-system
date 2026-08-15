"""
Pydantic schemas for WhatsApp messaging operations.

Covers:
- Message read/create payloads
- Chat list (conversation summary per lead)
- Instance/session management (QR code connection)
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ── Message Schemas ────────────────────────────────────────────────────

class WhatsAppMessageRead(BaseModel):
    """A single WhatsApp message returned to the frontend."""
    id: int
    lead_id: int | None
    user_id: int | None
    whatsapp_msg_id: str | None
    sender_phone: str
    receiver_phone: str
    direction: str
    content: str | None
    media_type: str | None
    media_url: str | None
    status: str
    timestamp: datetime

    model_config = {"from_attributes": True}


class WhatsAppSendMessage(BaseModel):
    """Payload for sending a new WhatsApp message from the CRM."""
    content: str = Field(..., min_length=1, max_length=4096)


# ── Chat List Schemas ──────────────────────────────────────────────────

class WhatsAppChatSummary(BaseModel):
    """Summary of a WhatsApp conversation with a lead (for the inbox sidebar)."""
    lead_id: int
    lead_name: str
    lead_phone: str
    lead_status: str | None = None
    last_message: str | None = None
    last_message_time: datetime | None = None
    unread_count: int = 0
    direction: str | None = None  # direction of last message


# ── Instance / Connection Schemas ──────────────────────────────────────

class InstanceCreateRequest(BaseModel):
    """Request to create a new Evolution API instance for a sales rep."""
    instance_name: str = Field(..., min_length=1, max_length=100)


class InstanceStatusResponse(BaseModel):
    """Status of a WhatsApp instance connection."""
    instance_name: str
    status: str  # "open" | "close" | "connecting"
    qr_code: str | None = None  # base64 QR code image when status is "connecting"


class WebhookVerification(BaseModel):
    """Evolution API webhook verification (not needed for Evo, but kept for safety)."""
    challenge: str | None = None
