"""
WhatsApp Message Model — stores all WhatsApp messages exchanged via Evolution API.

Each message is linked to a Lead (matched by phone number) and the
assigned sales rep's User record. The `whatsapp_msg_id` is the unique
message ID from WhatsApp, used for deduplication and status updates.

Direction:
    inbound  — customer → sales rep
    outbound — sales rep → customer (sent from our CRM)
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Integer, String, Enum, DateTime, ForeignKey, Text, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

import enum


class MessageDirection(str, enum.Enum):
    """Direction of a WhatsApp message."""
    inbound = "inbound"
    outbound = "outbound"


class MessageStatus(str, enum.Enum):
    """Delivery status of a WhatsApp message."""
    sent = "sent"
    delivered = "delivered"
    read = "read"
    failed = "failed"


class WhatsAppMessage(Base):
    """A single WhatsApp message exchanged between a sales rep and a lead.

    Messages are stored chronologically and linked to both the Lead
    (for CRM context) and the User (for rep-specific inbox filtering).
    """

    __tablename__ = "whatsapp_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    lead_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True,
        comment="NULL if the phone number could not be matched to a lead",
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True,
        comment="The sales rep who owns this conversation",
    )

    # WhatsApp-level identifiers
    whatsapp_msg_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True,
        comment="Unique message ID from WhatsApp, used for dedup",
    )
    instance_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Evolution API instance name (e.g. rep1_session)",
    )

    # Participants
    sender_phone: Mapped[str] = mapped_column(String(50), nullable=False)
    receiver_phone: Mapped[str] = mapped_column(String(50), nullable=False)

    direction: Mapped[MessageDirection] = mapped_column(
        Enum(MessageDirection, name="message_direction", create_constraint=True),
        nullable=False,
    )

    # Content
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="image | video | audio | document | null for text",
    )
    media_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Delivery status
    status: Mapped[MessageStatus] = mapped_column(
        Enum(MessageStatus, name="message_status", create_constraint=True),
        nullable=False,
        default=MessageStatus.sent,
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Composite index for fetching conversation threads efficiently
    __table_args__ = (
        Index("ix_wa_lead_timestamp", "lead_id", "timestamp"),
    )

    # ── Relationships ──────────────────────────────────────────────────
    lead: Mapped["Lead | None"] = relationship(          # noqa: F821
        "Lead", back_populates="whatsapp_messages", lazy="selectin",
    )
    user: Mapped["User | None"] = relationship(          # noqa: F821
        "User", back_populates="whatsapp_messages", lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<WhatsAppMessage id={self.id} dir={self.direction.value} lead_id={self.lead_id}>"
