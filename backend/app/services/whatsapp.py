"""
WhatsApp Service — Evolution API client and message processing logic.

Handles:
1. HTTP communication with the self-hosted Evolution API instance.
2. Incoming message processing (phone→lead matching, DB persistence, timeline logging).
3. Outbound message sending via Evolution API.

The Evolution API runs as a sibling Railway service and exposes a REST API
authenticated by a global API key.
"""

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.lead import Lead
from app.models.user import User
from app.models.interaction import LeadTimeline
from app.models.whatsapp_message import WhatsAppMessage, MessageDirection, MessageStatus

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Evolution API HTTP Client
# ═══════════════════════════════════════════════════════════════════════

class EvolutionAPIClient:
    """Thin wrapper around the Evolution API REST endpoints.

    All methods are async and use httpx for non-blocking HTTP calls.
    """

    def __init__(self):
        url = (settings.EVOLUTION_API_URL or "").strip().rstrip("/")
        if url and not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
        self.base_url = url
        self.api_key = settings.EVOLUTION_API_KEY
        self.headers = {"apikey": self.api_key, "Content-Type": "application/json"}

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    async def create_instance(self, instance_name: str) -> dict:
        """Create a new WhatsApp Web session instance.

        Returns the instance details including connection status.
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self._url("/instance/create"),
                headers=self.headers,
                json={
                    "instanceName": instance_name,
                    "qrcode": True,
                    "integration": "WHATSAPP-BAILEYS",
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def get_instance_status(self, instance_name: str) -> dict:
        """Check the connection status of an instance."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                self._url(f"/instance/connectionState/{instance_name}"),
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_qr_code(self, instance_name: str) -> dict:
        """Fetch the QR code for an instance that's waiting for scan."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                self._url(f"/instance/connect/{instance_name}"),
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def send_text_message(self, instance_name: str, phone: str, text: str) -> dict:
        """Send a text message via the connected WhatsApp instance.

        Args:
            instance_name: The Evolution API session name.
            phone: Recipient phone in international format (e.g. '919876543210').
            text: Message text content.
        """
        # Normalise phone: strip +, spaces, dashes
        clean_phone = phone.replace("+", "").replace(" ", "").replace("-", "")

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self._url(f"/message/sendText/{instance_name}"),
                headers=self.headers,
                json={
                    "number": clean_phone,
                    "text": text,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def logout_instance(self, instance_name: str) -> dict:
        """Disconnect (logout) an instance without deleting it."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.delete(
                self._url(f"/instance/logout/{instance_name}"),
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def list_instances(self) -> list[dict]:
        """List all registered instances."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                self._url("/instance/fetchInstances"),
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()


# Singleton-ish — imported as `from app.services.whatsapp import evo_client`
evo_client = EvolutionAPIClient()


# ═══════════════════════════════════════════════════════════════════════
# Message Processing
# ═══════════════════════════════════════════════════════════════════════

def _normalise_phone(phone: str) -> str:
    """Strip +, spaces, dashes from a phone number for comparison."""
    return phone.replace("+", "").replace(" ", "").replace("-", "").strip()


async def match_lead_by_phone(db: AsyncSession, phone: str) -> Lead | None:
    """Find a lead whose phone_number matches the given WhatsApp phone.

    Tries both raw and normalised comparison.
    """
    clean = _normalise_phone(phone)
    result = await db.execute(
        select(Lead).where(
            func.replace(func.replace(func.replace(
                Lead.phone_number, "+", ""), " ", ""), "-", "") == clean
        )
    )
    return result.scalar_one_or_none()


async def process_incoming_message(
    db: AsyncSession,
    *,
    instance_name: str,
    sender_phone: str,
    receiver_phone: str,
    content: str | None,
    whatsapp_msg_id: str | None,
    media_type: str | None = None,
    media_url: str | None = None,
    timestamp: datetime | None = None,
) -> WhatsAppMessage:
    """Process an inbound WhatsApp message from the Evolution API webhook.

    1. Match sender phone to a Lead.
    2. Find the assigned sales rep.
    3. Save the WhatsAppMessage row.
    4. Log a LeadTimeline entry for AI context.
    """
    # 1. Match lead
    lead = await match_lead_by_phone(db, sender_phone)
    lead_id = lead.id if lead else None
    user_id = lead.assigned_rep_id if lead else None

    # 2. Dedup — skip if we already stored this message
    if whatsapp_msg_id:
        existing = await db.execute(
            select(WhatsAppMessage).where(WhatsAppMessage.whatsapp_msg_id == whatsapp_msg_id)
        )
        if existing.scalar_one_or_none():
            logger.debug("Duplicate message %s, skipping", whatsapp_msg_id)
            return existing.scalar_one_or_none()

    # 3. Persist message
    msg = WhatsAppMessage(
        lead_id=lead_id,
        user_id=user_id,
        whatsapp_msg_id=whatsapp_msg_id,
        instance_name=instance_name,
        sender_phone=sender_phone,
        receiver_phone=receiver_phone,
        direction=MessageDirection.inbound,
        content=content,
        media_type=media_type,
        media_url=media_url,
        status=MessageStatus.delivered,
        timestamp=timestamp or datetime.now(timezone.utc),
    )
    db.add(msg)

    # 4. Log to LeadTimeline (only if matched to a lead)
    if lead_id:
        preview = (content or "")[:200]
        timeline_entry = LeadTimeline(
            lead_id=lead_id,
            user_id=user_id,
            event_type="whatsapp_message",
            event_metadata={
                "direction": "inbound",
                "sender_phone": sender_phone,
                "content_preview": preview,
                "media_type": media_type,
            },
        )
        db.add(timeline_entry)

    await db.commit()
    await db.refresh(msg)
    return msg


async def save_outbound_message(
    db: AsyncSession,
    *,
    lead_id: int,
    user_id: int,
    instance_name: str,
    sender_phone: str,
    receiver_phone: str,
    content: str,
    whatsapp_msg_id: str | None = None,
) -> WhatsAppMessage:
    """Save an outbound message sent from the CRM and log to timeline."""
    msg = WhatsAppMessage(
        lead_id=lead_id,
        user_id=user_id,
        whatsapp_msg_id=whatsapp_msg_id,
        instance_name=instance_name,
        sender_phone=sender_phone,
        receiver_phone=receiver_phone,
        direction=MessageDirection.outbound,
        content=content,
        status=MessageStatus.sent,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(msg)

    # Log timeline
    preview = content[:200]
    timeline_entry = LeadTimeline(
        lead_id=lead_id,
        user_id=user_id,
        event_type="whatsapp_message",
        event_metadata={
            "direction": "outbound",
            "receiver_phone": receiver_phone,
            "content_preview": preview,
        },
    )
    db.add(timeline_entry)

    await db.commit()
    await db.refresh(msg)
    return msg
