"""
WhatsApp Service — Evolution API client and message processing logic.

Handles:
1. HTTP communication with the self-hosted Evolution API instance.
2. Incoming message processing (phone->lead matching, DB persistence, timeline logging).
3. Outbound message sending via Evolution API.
4. Fast, comprehensive historical message syncing across instances.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select, func, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.lead import Lead
from app.models.user import User
from app.models.interaction import LeadTimeline, Notification
from app.models.whatsapp_message import WhatsAppMessage, MessageDirection, MessageStatus

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# Phone & JID Normalization Helpers
# ═══════════════════════════════════════════════════════════════════════

def _extract_digits(phone: Any) -> str:
    """Extract only digit characters from a string or number."""
    if not phone:
        return ""
    return re.sub(r"\D", "", str(phone))


def _normalise_phone(phone: Any) -> str:
    """Strip non-digits from a phone number for comparison."""
    return _extract_digits(phone)


def _normalise_phone_for_wa(phone: Any) -> str:
    """Normalize phone to international format without + (default 91 for 10-digit Indian numbers)."""
    digits = _extract_digits(phone)
    if not digits:
        return ""
    if len(digits) == 10:
        return f"91{digits}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"91{digits[1:]}"
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def extract_contact_phone_from_message(raw_msg: dict) -> str:
    """Extract real contact phone number (international digits) from a WhatsApp/Evolution message dict.

    Supports:
    - Standard WhatsApp JIDs (@s.whatsapp.net)
    - Multi-device JIDs (:0@s.whatsapp.net)
    - WhatsApp Privacy LIDs (@lid) via remoteJidAlt or participantAlt
    - Direct number fields
    """
    if not isinstance(raw_msg, dict):
        return ""

    key = raw_msg.get("key", {}) if isinstance(raw_msg.get("key"), dict) else {}

    candidates = [
        key.get("remoteJidAlt"),
        key.get("participantAlt"),
        raw_msg.get("remoteJidAlt"),
        raw_msg.get("participantAlt"),
        key.get("remoteJid"),
        raw_msg.get("remoteJid"),
        raw_msg.get("chatId"),
        raw_msg.get("from"),
        raw_msg.get("to"),
        raw_msg.get("sender"),
        raw_msg.get("receiver"),
    ]

    # Priority 1: Pick non-lid, non-group standard WhatsApp strings
    for c in candidates:
        if not c:
            continue
        c_str = str(c)
        if any(x in c_str for x in ("@g.us", "@broadcast", "@newsletter", "@lid")):
            continue
        user_part = c_str.split("@")[0].split(":")[0]
        digits = re.sub(r"\D", "", user_part)
        if len(digits) >= 10:
            return digits

    # Priority 2: Fallback to any digits in candidates (ignoring groups/broadcasts)
    for c in candidates:
        if not c:
            continue
        c_str = str(c)
        if "@g.us" in c_str or "@broadcast" in c_str or "@newsletter" in c_str:
            continue
        user_part = c_str.split("@")[0].split(":")[0]
        digits = re.sub(r"\D", "", user_part)
        if digits:
            return digits

    return ""


def extract_content_and_media(message_obj: Any, raw: Optional[dict] = None) -> Tuple[str, Optional[str]]:
    """Extract clean text content and media_type from an Evolution API / Baileys message."""
    raw = raw or {}

    if isinstance(message_obj, str):
        try:
            import json
            message_obj = json.loads(message_obj)
        except Exception:
            return message_obj.strip(), None

    if not isinstance(message_obj, dict):
        # Fallback to top-level raw fields
        for field in ["body", "text", "caption", "content"]:
            val = raw.get(field)
            if val and isinstance(val, str) and val.strip():
                return val.strip(), None
        return "", None

    # Handle ephemeral/view-once wrappers
    if "ephemeralMessage" in message_obj and isinstance(message_obj["ephemeralMessage"], dict):
        message_obj = message_obj["ephemeralMessage"].get("message", message_obj)
    if "viewOnceMessage" in message_obj and isinstance(message_obj["viewOnceMessage"], dict):
        message_obj = message_obj["viewOnceMessage"].get("message", message_obj)
    if "viewOnceMessageV2" in message_obj and isinstance(message_obj["viewOnceMessageV2"], dict):
        message_obj = message_obj["viewOnceMessageV2"].get("message", message_obj)

    # 1. Plain text conversation
    if "conversation" in message_obj and message_obj["conversation"]:
        return str(message_obj["conversation"]).strip(), None

    # 2. Extended text message (links, quotes, formatting)
    if "extendedTextMessage" in message_obj and isinstance(message_obj["extendedTextMessage"], dict):
        text = message_obj["extendedTextMessage"].get("text", "")
        if text:
            return str(text).strip(), None

    # 3. Media messages
    media_map = [
        ("imageMessage", "image", "caption", "[Image]"),
        ("videoMessage", "video", "caption", "[Video]"),
        ("audioMessage", "audio", None, "[Voice Note]"),
        ("documentMessage", "document", "fileName", "[Document]"),
        ("stickerMessage", "sticker", None, "[Sticker]"),
        ("contactMessage", "contact", "displayName", "[Contact]"),
        ("locationMessage", "location", "name", "[Location]"),
    ]

    for key, media_type, text_field, default_text in media_map:
        if key in message_obj and isinstance(message_obj[key], dict):
            obj = message_obj[key]
            text = (obj.get(text_field) if text_field else None) or obj.get("caption") or default_text
            return str(text).strip(), media_type

    # 4. Reaction messages
    if "reactionMessage" in message_obj and isinstance(message_obj["reactionMessage"], dict):
        emoji = message_obj["reactionMessage"].get("text", "")
        return (f"Reacted {emoji}" if emoji else ""), "reaction"

    # 5. Buttons / Template / Interactive messages
    if "templateButtonReplyMessage" in message_obj:
        return str(message_obj["templateButtonReplyMessage"].get("selectedDisplayText", "[Button Reply]")).strip(), None
    if "buttonsResponseMessage" in message_obj:
        return str(message_obj["buttonsResponseMessage"].get("selectedDisplayText", "[Button Response]")).strip(), None
    if "listResponseMessage" in message_obj:
        return str(message_obj["listResponseMessage"].get("title", "[List Selection]")).strip(), None

    # 6. Top-level raw fallback
    for field in ["body", "text", "caption"]:
        val = raw.get(field)
        if val and isinstance(val, str) and val.strip():
            return val.strip(), None

    return "", None


def extract_timestamp(raw: dict) -> datetime:
    """Extract and parse timestamp from an Evolution API / Baileys message dict."""
    if not isinstance(raw, dict):
        return datetime.now(timezone.utc)

    # Try integer unix epoch timestamp
    for key in ["messageTimestamp", "timestamp", "date"]:
        val = raw.get(key)
        if val is not None:
            try:
                ts_int = int(val)
                if ts_int > 1e11:
                    ts_int = int(ts_int / 1000)
                return datetime.fromtimestamp(ts_int, tz=timezone.utc)
            except (ValueError, TypeError, OSError):
                pass

    # Try ISO string format
    for key in ["createdAt", "created_at", "date", "updatedAt"]:
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════
# Evolution API HTTP Client
# ═══════════════════════════════════════════════════════════════════════

class EvolutionAPIClient:
    """Async client for the self-hosted Evolution API REST service."""

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
        """Create a new WhatsApp Web session instance."""
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
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(
                    self._url(f"/instance/connectionState/{instance_name}"),
                    headers=self.headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    state = data.get("instance", {}).get("state") or data.get("state")
                    if state == "open":
                        return data
            except Exception as e:
                logger.debug("get_instance_status direct check for %s: %s", instance_name, e)

            # Fallback: check all active instances
            try:
                list_resp = await client.get(self._url("/instance/fetchInstances"), headers=self.headers)
                if list_resp.status_code == 200:
                    instances = list_resp.json() if isinstance(list_resp.json(), list) else []
                    open_inst = next((i for i in instances if i.get("connectionStatus") == "open"), None)
                    if open_inst:
                        return {"instance": {"instanceName": open_inst.get("name"), "state": "open"}}
                    target = next((i for i in instances if i.get("name") == instance_name), None)
                    if target:
                        return {"instance": {"instanceName": instance_name, "state": target.get("connectionStatus", "close")}}
            except Exception as e:
                logger.debug("get_instance_status fallback check: %s", e)

            return {"instance": {"instanceName": instance_name, "state": "close"}}

    async def get_qr_code(self, instance_name: str) -> dict:
        """Fetch the QR code for an instance that is waiting for scan."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                self._url(f"/instance/connect/{instance_name}"),
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def send_text_message(self, instance_name: str, phone: str, text: str) -> dict:
        """Send a text message via the connected WhatsApp instance.

        Automatically falls back to any available open instance if the requested one fails.
        """
        clean_phone = _normalise_phone_for_wa(phone)

        async with httpx.AsyncClient(timeout=25) as client:
            # 1. Try requested instance
            if instance_name:
                try:
                    resp = await client.post(
                        self._url(f"/message/sendText/{instance_name}"),
                        headers=self.headers,
                        json={"number": clean_phone, "text": text},
                    )
                    if resp.status_code in (200, 201):
                        return resp.json()
                except Exception as e:
                    logger.warning("send_text_message via %s failed: %s", instance_name, e)

            # 2. Fallback to any open instance
            try:
                list_resp = await client.get(self._url("/instance/fetchInstances"), headers=self.headers)
                if list_resp.status_code == 200:
                    instances = list_resp.json() if isinstance(list_resp.json(), list) else []
                    for inst in instances:
                        if inst.get("connectionStatus") == "open" and inst.get("name") != instance_name:
                            fb_name = inst.get("name")
                            resp = await client.post(
                                self._url(f"/message/sendText/{fb_name}"),
                                headers=self.headers,
                                json={"number": clean_phone, "text": text},
                            )
                            if resp.status_code in (200, 201):
                                logger.info("send_text_message succeeded via fallback %s", fb_name)
                                return resp.json()
            except Exception as e:
                logger.error("send_text_message fallback error: %s", e)

            raise httpx.HTTPStatusError("No connected WhatsApp instance available to send message", request=None, response=None)

    async def logout_instance(self, instance_name: str) -> dict:
        """Disconnect (logout) an instance."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.delete(
                self._url(f"/instance/logout/{instance_name}"),
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def list_instances(self) -> list[dict]:
        """List all registered instances."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                self._url("/instance/fetchInstances"),
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _parse_message_records(data: Any) -> list[dict]:
        """Extract a clean list of message dicts from any Evolution API response format."""
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]

        if not isinstance(data, dict):
            return []

        # Check top-level keys
        for key in ["messages", "records", "data", "rows", "items", "response", "result"]:
            val = data.get(key)
            if isinstance(val, list) and val and isinstance(val[0], dict):
                return val
            if isinstance(val, dict):
                for subkey in ["records", "rows", "data", "messages", "items"]:
                    inner = val.get(subkey)
                    if isinstance(inner, list) and inner and isinstance(inner[0], dict):
                        return inner

        # Recursive fallback search
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                if any("key" in d or "message" in d or "id" in d for d in v[:3]):
                    return v
            elif isinstance(v, dict):
                found = EvolutionAPIClient._parse_message_records(v)
                if found:
                    return found

        return []

    async def fetch_messages(
        self,
        instance_name: str,
        phone: str,
        count: int = 100,
    ) -> list[dict]:
        """Fetch historical messages from Evolution API for a specific contact phone number.

        Searches candidate instances in parallel, resolves both standard JIDs and privacy @lid
        addresses, and returns deduplicated messages.
        """
        digits = _extract_digits(phone)
        if not digits:
            return []

        suffix10 = digits[-10:] if len(digits) >= 10 else digits
        clean_12 = f"91{suffix10}" if len(suffix10) == 10 else digits

        candidate_jids = {
            f"{clean_12}@s.whatsapp.net",
            f"{digits}@s.whatsapp.net",
            f"{suffix10}@s.whatsapp.net",
        }

        def _is_contact_message(m: dict) -> bool:
            """Check if a message belongs to this contact phone number."""
            if not isinstance(m, dict):
                return False

            key = m.get("key", {}) if isinstance(m.get("key"), dict) else {}

            # Exclude groups, broadcasts, newsletters
            for raw_jid in [key.get("remoteJid"), m.get("remoteJid"), m.get("chatId")]:
                if raw_jid and any(x in str(raw_jid) for x in ("@g.us", "@broadcast", "@newsletter")):
                    return False

            msg_phone = extract_contact_phone_from_message(m)
            if msg_phone:
                if msg_phone == clean_12 or msg_phone == digits:
                    return True
                if len(suffix10) >= 10 and (msg_phone.endswith(suffix10) or suffix10 in msg_phone):
                    return True

            for jid_val in [key.get("remoteJidAlt"), key.get("remoteJid"), key.get("participantAlt"), m.get("remoteJid")]:
                if jid_val:
                    j_str = str(jid_val)
                    if j_str in candidate_jids:
                        return True
                    j_clean = j_str.split(":")[0] + ("@" + j_str.split("@")[1] if "@" in j_str else "")
                    if j_clean in candidate_jids:
                        return True

            return False

        async with httpx.AsyncClient(timeout=12) as client:
            # 1. Discover all candidate instances
            candidate_instances = []
            if instance_name:
                candidate_instances.append(instance_name)

            try:
                list_resp = await client.get(self._url("/instance/fetchInstances"), headers=self.headers)
                if list_resp.status_code == 200:
                    inst_data = list_resp.json() if isinstance(list_resp.json(), list) else []
                    for inst in inst_data:
                        name = inst.get("name")
                        status = inst.get("connectionStatus")
                        if name and status == "open" and name not in candidate_instances:
                            candidate_instances.append(name)
            except Exception as e:
                logger.debug("Failed to list candidate instances: %s", e)

            # 2. Parallel Query Function per instance
            async def _query_instance(inst: str) -> list[dict]:
                collected = []

                # Strategy 1: Direct number query
                for num in candidate_numbers:
                    try:
                        resp = await client.post(
                            self._url(f"/chat/findMessages/{inst}"),
                            headers=self.headers,
                            json={"number": num, "limit": count},
                        )
                        if resp.status_code == 200:
                            records = self._parse_message_records(resp.json())
                            collected.extend([m for m in records if _is_contact_message(m)])
                    except Exception as e:
                        logger.debug("findMessages number=%s on %s error: %s", num, inst, e)

                # Strategy 2: where remoteJidAlt and remoteJid filters
                for jid in candidate_jids:
                    for payload in [
                        {"where": {"key": {"remoteJidAlt": jid}}, "limit": count},
                        {"where": {"key": {"remoteJid": jid}}, "limit": count},
                    ]:
                        try:
                            resp = await client.post(
                                self._url(f"/chat/findMessages/{inst}"),
                                headers=self.headers,
                                json=payload,
                            )
                            if resp.status_code == 200:
                                records = self._parse_message_records(resp.json())
                                collected.extend([m for m in records if _is_contact_message(m)])
                        except Exception:
                            pass

                # Strategy 3: General limit fallback
                if not collected:
                    try:
                        resp = await client.post(
                            self._url(f"/chat/findMessages/{inst}"),
                            headers=self.headers,
                            json={"limit": count},
                        )
                        if resp.status_code == 200:
                            records = self._parse_message_records(resp.json())
                            collected.extend([m for m in records if _is_contact_message(m)])
                    except Exception:
                        pass

                return collected

            candidate_numbers = list(dict.fromkeys([clean_12, digits, suffix10]))
            results = await asyncio.gather(*(_query_instance(inst) for inst in candidate_instances if inst))
            all_records = [m for sublist in results for m in sublist]

            # Deduplicate by message ID or timestamp
            seen_ids = set()
            deduped = []
            for m in all_records:
                key = m.get("key", {}) if isinstance(m.get("key"), dict) else {}
                m_id = str(key.get("id") or m.get("id") or m.get("whatsapp_msg_id") or "")
                if m_id and m_id in seen_ids:
                    continue
                if m_id:
                    seen_ids.add(m_id)
                deduped.append(m)

            logger.info("fetch_messages: returning %d messages for %s", len(deduped), digits)
            return deduped[:count]


# Singleton instance
evo_client = EvolutionAPIClient()


# ═══════════════════════════════════════════════════════════════════════
# Database Matching & Message Persistence Helpers
# ═══════════════════════════════════════════════════════════════════════

async def match_lead_by_phone(db: AsyncSession, phone: str, assigned_rep_id: Optional[int] = None) -> Optional[Lead]:
    """Find a lead in the database whose phone number matches the WhatsApp contact phone.

    Handles 10-digit, 11-digit (leading 0), and 12-digit (91 prefix) formats.
    """
    digits = _extract_digits(phone)
    if not digits:
        return None

    suffix10 = digits[-10:] if len(digits) >= 10 else digits
    clean_12 = f"91{suffix10}" if len(suffix10) == 10 else digits

    # Try rep-specific match first
    if assigned_rep_id is not None:
        query = select(Lead).where(
            Lead.assigned_rep_id == assigned_rep_id,
            or_(
                Lead.phone_number == digits,
                Lead.phone_number == clean_12,
                Lead.phone_number == suffix10,
                Lead.phone_number.like(f"%{suffix10}"),
            ),
        )
        res = await db.execute(query)
        lead = res.scalars().first()
        if lead:
            return lead

    # Global lead match fallback
    query = select(Lead).where(
        or_(
            Lead.phone_number == digits,
            Lead.phone_number == clean_12,
            Lead.phone_number == suffix10,
            Lead.phone_number.like(f"%{suffix10}"),
        )
    )
    res = await db.execute(query)
    return res.scalars().first()


async def upsert_message(
    db: AsyncSession,
    *,
    lead_id: Optional[int],
    user_id: Optional[int],
    instance_name: str,
    sender_phone: str,
    receiver_phone: str,
    direction: MessageDirection,
    content: Optional[str],
    whatsapp_msg_id: Optional[str] = None,
    media_type: Optional[str] = None,
    media_url: Optional[str] = None,
    status: MessageStatus = MessageStatus.delivered,
    timestamp: Optional[datetime] = None,
) -> Tuple[WhatsAppMessage, bool]:
    """Insert or update a WhatsAppMessage row, ensuring deduplication."""
    if whatsapp_msg_id:
        existing = await db.execute(
            select(WhatsAppMessage).where(WhatsAppMessage.whatsapp_msg_id == str(whatsapp_msg_id))
        )
        msg = existing.scalars().first()
        if msg:
            # Update missing attributes
            if lead_id and not msg.lead_id:
                msg.lead_id = lead_id
            if user_id and not msg.user_id:
                msg.user_id = user_id
            if content and not msg.content:
                msg.content = content
            if media_type and not msg.media_type:
                msg.media_type = media_type
            return msg, False

    msg = WhatsAppMessage(
        lead_id=lead_id,
        user_id=user_id,
        whatsapp_msg_id=str(whatsapp_msg_id) if whatsapp_msg_id else None,
        instance_name=instance_name,
        sender_phone=sender_phone,
        receiver_phone=receiver_phone,
        direction=direction,
        content=content,
        media_type=media_type,
        media_url=media_url,
        status=status,
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
    content: Optional[str],
    whatsapp_msg_id: Optional[str],
    media_type: Optional[str] = None,
    media_url: Optional[str] = None,
    timestamp: Optional[datetime] = None,
    is_from_me: bool = False,
) -> WhatsAppMessage:
    """Process an inbound or webhook WhatsApp message."""
    rep_id = None
    if instance_name and instance_name.startswith("rep_"):
        try:
            rep_id = int(instance_name.replace("rep_", ""))
        except ValueError:
            pass

    lead_phone = receiver_phone if is_from_me else sender_phone
    lead = await match_lead_by_phone(db, lead_phone, assigned_rep_id=rep_id)

    lead_id = lead.id if lead else None
    user_id = lead.assigned_rep_id if lead else rep_id

    direction = MessageDirection.outbound if is_from_me else MessageDirection.inbound

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

    # Log to LeadTimeline and create in-app Notification if new and matched to a lead
    if is_new and lead_id and user_id:
        preview = (content or "")[:200]
        timeline_entry = LeadTimeline(
            lead_id=lead_id,
            user_id=user_id,
            event_type="whatsapp_message",
            event_metadata={
                "direction": "inbound" if not is_from_me else "outbound",
                "sender_phone": sender_phone,
                "content_preview": preview,
                "media_type": media_type,
            },
        )
        db.add(timeline_entry)

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
    whatsapp_msg_id: Optional[str] = None,
) -> WhatsAppMessage:
    """Save an outbound message sent from the CRM and log to timeline."""
    msg, _ = await upsert_message(
        db,
        lead_id=lead_id,
        user_id=user_id,
        instance_name=instance_name,
        sender_phone=sender_phone,
        receiver_phone=receiver_phone,
        direction=MessageDirection.outbound,
        content=content,
        whatsapp_msg_id=whatsapp_msg_id,
        status=MessageStatus.sent,
        timestamp=datetime.now(timezone.utc),
    )

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
