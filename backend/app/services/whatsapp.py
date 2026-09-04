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

    async def fetch_messages(
        self,
        instance_name: str,
        phone_or_jid: str,
        count: int = 50,
    ) -> list[dict]:
        """Fetch historical messages from Evolution API for a specific contact chat.

        Queries Evolution API for the specific contact's remoteJid.
        Filters strictly so ONLY messages belonging to this contact are returned.
        """
        import re

        raw_phone = phone_or_jid.split("@")[0].split(":")[0] if "@" in phone_or_jid else phone_or_jid
        digits = re.sub(r"\D", "", str(raw_phone or ""))
        if not digits:
            return []

        suffix10 = digits[-10:] if len(digits) >= 10 else digits
        clean_12 = f"91{suffix10}" if len(suffix10) == 10 else digits

        # Construct candidate JIDs for this contact
        candidate_jids = []
        if "@s.whatsapp.net" in phone_or_jid or "@lid" in phone_or_jid:
            candidate_jids.append(phone_or_jid)
        if len(digits) == 10:
            candidate_jids.append(f"91{digits}@s.whatsapp.net")
            candidate_jids.append(f"{digits}@s.whatsapp.net")
        elif len(digits) == 11 and digits.startswith("0"):
            candidate_jids.append(f"91{digits[1:]}@s.whatsapp.net")
            candidate_jids.append(f"{digits[1:]}@s.whatsapp.net")
        elif len(digits) == 12 and digits.startswith("91"):
            candidate_jids.append(f"{digits}@s.whatsapp.net")
            candidate_jids.append(f"{digits[2:]}@s.whatsapp.net")
        else:
            candidate_jids.append(f"{digits}@s.whatsapp.net")

        seen = set()
        target_jids = []
        for j in candidate_jids:
            if j not in seen:
                seen.add(j)
                target_jids.append(j)

        def _is_chat_message(m: dict) -> bool:
            """Check if a message object belongs strictly to this contact."""
            if not isinstance(m, dict):
                return False
            key = m.get("key", {}) if isinstance(m.get("key"), dict) else {}
            jid = str(key.get("remoteJid") or m.get("remoteJid") or "")
            # Exclude groups, status broadcasts, newsletters
            if not jid or "@g.us" in jid or "@broadcast" in jid or "@newsletter" in jid:
                return False
            
            # Check exact JID match
            if jid in target_jids:
                return True
            
            # Check phone digits match
            jid_phone = re.sub(r"\D", "", jid.split("@")[0].split(":")[0])
            if not jid_phone:
                return False
            if jid_phone == clean_12 or jid_phone == digits:
                return True
            if len(suffix10) == 10 and jid_phone.endswith(suffix10):
                return True
            return False

        def _parse_records(data) -> list[dict]:
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
            if isinstance(data, dict):
                msgs = data.get("messages")
                if isinstance(msgs, dict):
                    rec = msgs.get("records") or msgs.get("rows") or msgs.get("data")
                    if isinstance(rec, list):
                        return [d for d in rec if isinstance(d, dict)]
                elif isinstance(msgs, list):
                    return [d for d in msgs if isinstance(d, dict)]
                for k in ["records", "data", "rows", "items"]:
                    rec = data.get(k)
                    if isinstance(rec, list):
                        return [d for d in rec if isinstance(d, dict)]
            return []

        async with httpx.AsyncClient(timeout=12) as client:
            # Strategy 1: Direct findMessages with targeted where queries
            for jid in target_jids:
                for payload in [
                    {"where": {"remoteJid": jid}, "limit": count},
                    {"where": {"key": {"remoteJid": jid}}, "limit": count},
                    {"where": {"key.remoteJid": jid}, "limit": count},
                ]:
                    try:
                        resp = await client.post(
                            self._url(f"/chat/findMessages/{instance_name}"),
                            headers=self.headers,
                            json=payload,
                        )
                        if resp.status_code == 200:
                            recs = _parse_records(resp.json())
                            filtered = [r for r in recs if _is_chat_message(r)]
                            if filtered:
                                return filtered[:count]
                    except Exception as e:
                        logger.debug("findMessages payload failed for %s: %s", jid, e)

            # Strategy 2: Query findMessages with limit and filter strictly by this contact
            try:
                for fallback_payload in [{"limit": 100}, {}]:
                    resp = await client.post(
                        self._url(f"/chat/findMessages/{instance_name}"),
                        headers=self.headers,
                        json=fallback_payload,
                    )
                    if resp.status_code == 200:
                        recs = _parse_records(resp.json())
                        filtered = [r for r in recs if _is_chat_message(r)]
                        if filtered:
                            return filtered[:count]
            except Exception as e:
                logger.debug("findMessages fallback failed: %s", e)

            # Strategy 3: Check findChats for this specific contact
            try:
                c_resp = await client.post(
                    self._url(f"/chat/findChats/{instance_name}"),
                    headers=self.headers,
                    json={},
                )
                if c_resp.status_code >= 400:
                    c_resp = await client.get(
                        self._url(f"/chat/findChats/{instance_name}"),
                        headers=self.headers,
                    )
                if c_resp.status_code == 200:
                    chats = _parse_records(c_resp.json())
                    for ch in chats:
                        ch_jid = str(ch.get("remoteJid") or ch.get("id") or ch.get("jid") or "")
                        ch_phone = re.sub(r"\D", "", ch_jid.split("@")[0].split(":")[0])
                        if (suffix10 and suffix10 in ch_phone) or ch_jid in target_jids:
                            for p in [
                                {"where": {"remoteJid": ch_jid}, "limit": count},
                                {"where": {"key": {"remoteJid": ch_jid}}, "limit": count},
                            ]:
                                m_resp = await client.post(
                                    self._url(f"/chat/findMessages/{instance_name}"),
                                    headers=self.headers,
                                    json=p,
                                )
                                if m_resp.status_code == 200:
                                    recs = _parse_records(m_resp.json())
                                    filtered = [r for r in recs if _is_chat_message(r)]
                                    if filtered:
                                        return filtered[:count]
                            if ch.get("lastMessage") and isinstance(ch["lastMessage"], dict):
                                if _is_chat_message(ch["lastMessage"]):
                                    return [ch["lastMessage"]]
            except Exception as e:
                logger.debug("findChats lookup failed: %s", e)

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
    2. Find the assigned sales rep.
    3. Save the WhatsAppMessage row.
    4. Log a LeadTimeline entry for AI context.
    """
    # 1. Match lead (only match leads assigned to this WhatsApp instance's user!)
    rep_id = None
    if instance_name and instance_name.startswith("rep_"):
        try:
            rep_id = int(instance_name.replace("rep_", ""))
        except ValueError:
            pass

    lead_phone = receiver_phone if is_from_me else sender_phone
    lead = await match_lead_by_phone(db, lead_phone, assigned_rep_id=rep_id)
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
        direction=MessageDirection.outbound if is_from_me else MessageDirection.inbound,
        content=content,
        media_type=media_type,
        media_url=media_url,
        status=MessageStatus.delivered,
        timestamp=timestamp or datetime.now(timezone.utc),
    )
    db.add(msg)

    # 4. Log to LeadTimeline and create in-app Notification (only if matched to a lead)
    if lead_id and user_id:
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

        # Only notify if it's an inbound message
        if not is_from_me:
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

    if lead_id:
        from sqlalchemy import delete
        await db.execute(
            delete(WhatsAppMessage).where(
                WhatsAppMessage.lead_id == lead_id,
                WhatsAppMessage.content == "[Chat Initialised - No previous history found]",
            )
        )

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

    from sqlalchemy import delete
    await db.execute(
        delete(WhatsAppMessage).where(
            WhatsAppMessage.lead_id == lead_id,
            WhatsAppMessage.content == "[Chat Initialised - No previous history found]",
        )
    )

    await db.commit()
    await db.refresh(msg)
    return msg
