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
from app.models.interaction import LeadTimeline, Notification
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

    @staticmethod
    def _parse_message_response(data) -> list[dict]:
        """Parse Evolution API findMessages response into a flat list of message dicts.

        Evolution API v2.x can return messages in several wrapper formats.
        This normalises all of them into a simple list.
        """
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        if isinstance(data, dict):
            for key in ["messages", "records", "data", "rows", "items"]:
                val = data.get(key)
                if isinstance(val, list):
                    return [d for d in val if isinstance(d, dict)]
                if isinstance(val, dict):
                    inner = val.get("records") or val.get("rows") or val.get("data")
                    if isinstance(inner, list):
                        return [d for d in inner if isinstance(d, dict)]
        return []

    async def fetch_messages(
        self,
        instance_name: str,
        phone: str,
        count: int = 100,
    ) -> list[dict]:
        """Fetch message history from Evolution API for a specific contact.

        Uses the correct Evolution API v2.3.7 format:
            POST /chat/findMessages/{instance}
            body: {"number": "<phone_with_country_code>"}

        Falls back to {"where": {"key": {"remoteJid": jid}}} for compatibility.

        Args:
            instance_name: The Evolution API session name (e.g. "rep_1").
            phone: Contact phone in any format — digits are extracted and normalised.
            count: Maximum number of messages to return (default 100).
        """
        import re

        digits = re.sub(r"\D", "", str(phone or ""))
        if not digits:
            return []

        # Normalize to 12-digit Indian format (91XXXXXXXXXX)
        if len(digits) == 10:
            digits = f"91{digits}"
        elif len(digits) == 11 and digits.startswith("0"):
            digits = f"91{digits[1:]}"

        jid = f"{digits}@s.whatsapp.net"

        async with httpx.AsyncClient(timeout=30) as client:
            # Strategy 1: Use "number" field (correct per Evolution API v2.3.7 docs)
            try:
                resp = await client.post(
                    self._url(f"/chat/findMessages/{instance_name}"),
                    headers=self.headers,
                    json={"number": digits},
                )
                if resp.status_code == 200:
                    messages = self._parse_message_response(resp.json())
                    if messages:
                        logger.info(
                            "fetch_messages: got %d messages for %s via number field",
                            len(messages), digits,
                        )
                        return messages[:count]
            except Exception as e:
                logger.warning("findMessages with number field failed: %s", e)

            # Strategy 2: Fallback with where.key.remoteJid (older API versions)
            try:
                resp = await client.post(
                    self._url(f"/chat/findMessages/{instance_name}"),
                    headers=self.headers,
                    json={"where": {"key": {"remoteJid": jid}}},
                )
                if resp.status_code == 200:
                    messages = self._parse_message_response(resp.json())
                    if messages:
                        logger.info(
                            "fetch_messages: got %d messages for %s via remoteJid fallback",
                            len(messages), jid,
                        )
                        return messages[:count]
            except Exception as e:
                logger.warning("findMessages with remoteJid fallback failed: %s", e)

        logger.info("fetch_messages: no messages found for %s", digits)
        return []


# Singleton-ish — imported as `from app.services.whatsapp import evo_client`
evo_client = EvolutionAPIClient()


# ═══════════════════════════════════════════════════════════════════════
# Message Processing & Normalization Helpers
# ═══════════════════════════════════════════════════════════════════════

def _extract_digits(phone: str) -> str:
    """Extract only digit characters from a string."""
    if not phone:
        return ""
    import re
    return re.sub(r"\D", "", str(phone))


def _normalise_phone(phone: str) -> str:
    """Strip non-digits from a phone number for comparison."""
    return _extract_digits(phone)


def _normalise_phone_for_wa(phone: str) -> str:
    """Normalize phone to international format without + (default 91 for Indian numbers)."""
    digits = _extract_digits(phone)
    if not digits:
        return ""
    if len(digits) == 11 and digits.startswith("0"):
        return f"91{digits[1:]}"
    if len(digits) == 10:
        return f"91{digits}"
    if len(digits) == 12 and digits.startswith("91"):
        return digits
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def extract_content_and_media(message_obj: dict | str | None, raw: dict | None = None) -> tuple[str, str | None]:
    """Extract clean text content and media_type from an Evolution API / Baileys message."""
    raw = raw or {}
    if isinstance(message_obj, str):
        try:
            import json
            message_obj = json.loads(message_obj)
        except Exception:
            return message_obj, None

    if not isinstance(message_obj, dict):
        content = raw.get("body") or raw.get("content") or raw.get("text") or ""
        return str(content).strip(), None

    # Unwrap ephemeral or viewOnce wrapper if present
    for wrapper in ["ephemeralMessage", "viewOnceMessage", "viewOnceMessageV2", "documentWithCaptionMessage"]:
        if wrapper in message_obj and isinstance(message_obj[wrapper], dict):
            inner = message_obj[wrapper].get("message", message_obj[wrapper])
            if isinstance(inner, dict):
                message_obj = inner

    media_type = None
    content = ""

    if "conversation" in message_obj and message_obj["conversation"]:
        content = str(message_obj["conversation"])
    elif "extendedTextMessage" in message_obj and isinstance(message_obj["extendedTextMessage"], dict):
        content = str(message_obj["extendedTextMessage"].get("text", ""))
    elif "imageMessage" in message_obj:
        media_type = "image"
        img = message_obj["imageMessage"] if isinstance(message_obj["imageMessage"], dict) else {}
        content = str(img.get("caption") or "[Image]")
    elif "videoMessage" in message_obj:
        media_type = "video"
        vid = message_obj["videoMessage"] if isinstance(message_obj["videoMessage"], dict) else {}
        content = str(vid.get("caption") or "[Video]")
    elif "audioMessage" in message_obj:
        media_type = "audio"
        content = "[Voice Note]"
    elif "documentMessage" in message_obj:
        media_type = "document"
        doc = message_obj["documentMessage"] if isinstance(message_obj["documentMessage"], dict) else {}
        content = str(doc.get("fileName") or doc.get("title") or "[Document]")
    elif "buttonsResponseMessage" in message_obj and isinstance(message_obj["buttonsResponseMessage"], dict):
        content = str(message_obj["buttonsResponseMessage"].get("selectedDisplayText") or "")
    elif "templateButtonReplyMessage" in message_obj and isinstance(message_obj["templateButtonReplyMessage"], dict):
        content = str(message_obj["templateButtonReplyMessage"].get("selectedDisplayText") or "")
    elif "listResponseMessage" in message_obj and isinstance(message_obj["listResponseMessage"], dict):
        content = str(message_obj["listResponseMessage"].get("title") or "")
    else:
        content = str(raw.get("body") or raw.get("content") or raw.get("text") or "")

    return content.strip(), media_type


def extract_timestamp(raw: dict) -> datetime:
    """Extract and parse timestamp as timezone-aware UTC datetime."""
    raw_ts = raw.get("messageTimestamp") or raw.get("timestamp") or raw.get("createdAt")
    if raw_ts is not None:
        try:
            if isinstance(raw_ts, (int, float)):
                val = float(raw_ts)
                if val > 1e11:  # milliseconds
                    val = val / 1000.0
                return datetime.fromtimestamp(val, tz=timezone.utc)
            elif isinstance(raw_ts, str):
                if raw_ts.isdigit():
                    val = float(raw_ts)
                    if val > 1e11:
                        val = val / 1000.0
                    return datetime.fromtimestamp(val, tz=timezone.utc)
                else:
                    return datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        except Exception:
            pass
    return datetime.now(timezone.utc)


async def match_lead_by_phone(db: AsyncSession, phone: str, assigned_rep_id: int | None = None) -> Lead | None:
    """Find a lead whose phone_number matches the given WhatsApp phone."""
    from sqlalchemy import or_

    digits = _extract_digits(phone)
    if not digits:
        return None

    clean_wa = _normalise_phone_for_wa(phone)
    suffix10 = digits[-10:] if len(digits) >= 10 else digits

    clean_lead = func.replace(
        func.replace(
            func.replace(
                func.replace(
                    func.replace(Lead.phone_number, "+", ""),
                    " ", ""
                ),
                "-", ""
            ),
            "(", ""
        ),
        ")", ""
    )

    conditions = [
        clean_lead == clean_wa,
        clean_lead == digits,
        func.concat("91", clean_lead) == clean_wa,
    ]
    if len(suffix10) == 10:
        conditions.append(func.right(clean_lead, 10) == suffix10)

    query = select(Lead).where(or_(*conditions))

    if assigned_rep_id is not None:
        query = query.where(Lead.assigned_rep_id == assigned_rep_id)

    result = await db.execute(query)
    return result.scalars().first()



async def upsert_message(
    db: AsyncSession,
    *,
    lead_id: int,
    user_id: int | None,
    instance_name: str,
    sender_phone: str,
    receiver_phone: str,
    direction: MessageDirection,
    content: str | None,
    whatsapp_msg_id: str | None,
    media_type: str | None = None,
    media_url: str | None = None,
    timestamp: datetime | None = None,
) -> tuple[WhatsAppMessage, bool]:
    """Insert a message if it doesn't already exist (by whatsapp_msg_id).

    Returns:
        (message, is_new): The message object and whether it was newly created.
    """
    # Dedup by whatsapp_msg_id
    if whatsapp_msg_id:
        existing_res = await db.execute(
            select(WhatsAppMessage).where(WhatsAppMessage.whatsapp_msg_id == str(whatsapp_msg_id))
        )
        existing = existing_res.scalar_one_or_none()
        if existing:
            # If it exists but wasn't linked to a lead, link it now
            changed = False
            if existing.lead_id is None and lead_id:
                existing.lead_id = lead_id
                existing.user_id = user_id
                existing.instance_name = instance_name
                changed = True
            if not existing.content and content:
                existing.content = content
                changed = True
            return existing, changed

    msg = WhatsAppMessage(
        lead_id=lead_id,
        user_id=user_id,
        whatsapp_msg_id=whatsapp_msg_id,
        instance_name=instance_name,
        sender_phone=sender_phone,
        receiver_phone=receiver_phone,
        direction=direction,
        content=content,
        media_type=media_type,
        media_url=media_url,
        status=MessageStatus.delivered,
        timestamp=timestamp or datetime.now(timezone.utc),
    )
    db.add(msg)
    return msg, True


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
    is_from_me: bool = False,
) -> WhatsAppMessage:
    """Process an inbound WhatsApp message from the Evolution API webhook.

    1. Match the correct phone number (sender if inbound, receiver if outbound) to a Lead.
    2. Use upsert_message() for dedup + persistence.
    3. Log a LeadTimeline entry for AI context.
    4. Create in-app notification for inbound messages.
    """
    # 1. Match lead (only match leads assigned to this WhatsApp instance's user)
    rep_id = None
    if instance_name and instance_name.startswith("rep_"):
        try:
            rep_id = int(instance_name.replace("rep_", ""))
        except ValueError:
            pass

    lead_phone = receiver_phone if is_from_me else sender_phone
    lead = await match_lead_by_phone(db, lead_phone, assigned_rep_id=rep_id)
    if not lead:
        logger.debug("WhatsApp message from/to %s is not a CRM lead. Ignored.", lead_phone)
        return None

    lead_id = lead.id
    user_id = lead.assigned_rep_id
    direction = MessageDirection.outbound if is_from_me else MessageDirection.inbound

    # 2. Dedup + persist via unified helper
    msg, is_new = await upsert_message(
        db,
        lead_id=lead_id,
        user_id=user_id,
        instance_name=instance_name,
        sender_phone=sender_phone,
        receiver_phone=receiver_phone,
        direction=direction,
        content=content,
        whatsapp_msg_id=whatsapp_msg_id,
        media_type=media_type,
        media_url=media_url,
        timestamp=timestamp,
    )

    if not is_new:
        # Duplicate — just commit any link updates and return
        await db.commit()
        return msg

    # 3. Log to LeadTimeline
    preview = (content or "")[:200]
    timeline_entry = LeadTimeline(
        lead_id=lead_id,
        user_id=user_id,
        event_type="whatsapp_message",
        event_metadata={
            "direction": direction.value,
            "sender_phone": sender_phone,
            "content_preview": preview,
            "media_type": media_type,
        },
    )
    db.add(timeline_entry)

    # 4. Notify on inbound messages only
    if not is_from_me and user_id:
        lead_display = lead.name or sender_phone
        notif = Notification(
            user_id=user_id,
            title=f"WhatsApp from {lead_display}",
            message=f"{preview or '[Media]'}",
            notification_type="whatsapp_message",
            link_type="lead",
            link_id=lead_id,
        )
        db.add(notif)

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
    msg, is_new = await upsert_message(
        db,
        lead_id=lead_id,
        user_id=user_id,
        instance_name=instance_name,
        sender_phone=sender_phone,
        receiver_phone=receiver_phone,
        direction=MessageDirection.outbound,
        content=content,
        whatsapp_msg_id=whatsapp_msg_id,
    )

    # Override status for CRM-sent messages
    msg.status = MessageStatus.sent

    if is_new:
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
