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
import re
from datetime import datetime, timezone
from typing import Optional

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

    def _parse_message_records(self, data) -> list[dict]:
        """Parse Evolution API findMessages response into a flat list of message records."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            records = (
                (data.get("messages") or {}).get("records")
                if isinstance(data.get("messages"), dict)
                else None
            ) or data.get("records") or data.get("data") or []
            if isinstance(records, list):
                return records
        return []

    async def find_contacts(self, instance_name: str) -> list[dict]:
        """Fetch all contacts for an instance from Evolution API."""
        async with httpx.AsyncClient(timeout=20) as client:
            try:
                resp = await client.post(
                    self._url(f"/chat/findContacts/{instance_name}"),
                    headers=self.headers,
                    json={},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        return data
                    if isinstance(data, dict):
                        return (
                            data.get("records")
                            or data.get("contacts")
                            or data.get("data")
                            or []
                        )
            except Exception as exc:
                logger.debug("findContacts POST failed for %s: %s", instance_name, exc)

            try:
                resp = await client.get(
                    self._url(f"/chat/findContacts/{instance_name}"),
                    headers=self.headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        return data
                    if isinstance(data, dict):
                        return (
                            data.get("records")
                            or data.get("contacts")
                            or data.get("data")
                            or []
                        )
            except Exception as exc:
                logger.debug("findContacts GET failed for %s: %s", instance_name, exc)
            return []

    async def find_chats(self, instance_name: str) -> list[dict]:
        """Fetch all chats for an instance from Evolution API."""
        async with httpx.AsyncClient(timeout=20) as client:
            try:
                resp = await client.post(
                    self._url(f"/chat/findChats/{instance_name}"),
                    headers=self.headers,
                    json={},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        return data
                    if isinstance(data, dict):
                        return (
                            data.get("records")
                            or data.get("chats")
                            or data.get("data")
                            or []
                        )
            except Exception as exc:
                logger.debug("findChats POST failed for %s: %s", instance_name, exc)

            try:
                resp = await client.get(
                    self._url(f"/chat/findChats/{instance_name}"),
                    headers=self.headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        return data
                    if isinstance(data, dict):
                        return (
                            data.get("records")
                            or data.get("chats")
                            or data.get("data")
                            or []
                        )
            except Exception as exc:
                logger.debug("findChats GET failed for %s: %s", instance_name, exc)
            return []

    async def resolve_jids_for_phone(self, instance_name: str, phone: str) -> list[str]:
        """Resolve all candidate WhatsApp JIDs (including @lid format) for a phone number.

        Queries Evolution API contacts and chats to discover if WhatsApp uses a privacy
        @lid identifier or @s.whatsapp.net for this contact.
        """
        digits = "".join(c for c in (phone or "") if c.isdigit())
        if not digits:
            return []

        candidates: list[str] = []
        seen = set()

        def add_candidate(jid: str | None):
            if not jid or not isinstance(jid, str):
                return
            jid = jid.strip()
            if not jid or "@g.us" in jid:  # Skip groups
                return
            if jid not in seen:
                seen.add(jid)
                candidates.append(jid)

        last10 = digits[-10:] if len(digits) >= 10 else digits

        # Standard formats to always include
        clean_wa = _normalise_phone_for_wa(phone)
        if clean_wa:
            add_candidate(f"{clean_wa}@s.whatsapp.net")
        if digits != clean_wa:
            add_candidate(f"{digits}@s.whatsapp.net")
        if len(digits) == 10:
            add_candidate(f"91{digits}@s.whatsapp.net")
        elif digits.startswith("91") and len(digits) > 10:
            add_candidate(f"{digits[2:]}@s.whatsapp.net")

        # Query contacts from Evolution API to find matching @lid or custom JID
        try:
            contacts = await self.find_contacts(instance_name)
            for c in contacts:
                if not isinstance(c, dict):
                    continue
                c_id = str(c.get("id") or "")
                c_jid = str(c.get("remoteJid") or "")
                c_alt = str(c.get("remoteJidAlt") or "")
                c_lid = str(c.get("lid") or "")
                c_num = str(c.get("number") or c.get("phoneNumber") or "")
                c_name = str(c.get("pushName") or c.get("name") or "")

                is_match = (
                    (last10 and (last10 in c_id or last10 in c_jid or last10 in c_num or last10 in c_name))
                    or (digits and (digits in c_id or digits in c_jid or digits in c_num))
                )

                if is_match:
                    if c_lid and "@" in c_lid:
                        add_candidate(c_lid)
                    if "@lid" in c_jid:
                        add_candidate(c_jid)
                    if "@lid" in c_id:
                        add_candidate(c_id)
                    if c_alt and "@" in c_alt:
                        add_candidate(c_alt)
                    if c_jid and "@" in c_jid:
                        add_candidate(c_jid)
                    if c_id and "@" in c_id:
                        add_candidate(c_id)
        except Exception as exc:
            logger.debug("Failed checking contacts for JID resolution: %s", exc)

        # Also query findChats to find active chat sessions
        try:
            chats = await self.find_chats(instance_name)
            for ch in chats:
                if not isinstance(ch, dict):
                    continue
                ch_id = str(ch.get("id") or "")
                ch_jid = str(ch.get("remoteJid") or "")
                ch_lid = str(ch.get("lid") or "")
                ch_phone = str(ch.get("phone") or "")

                is_match = (
                    (last10 and (last10 in ch_id or last10 in ch_jid or last10 in ch_phone))
                    or (digits and (digits in ch_id or digits in ch_jid or digits in ch_phone))
                )
                if is_match:
                    if ch_lid and "@" in ch_lid:
                        add_candidate(ch_lid)
                    if "@lid" in ch_jid:
                        add_candidate(ch_jid)
                    if "@lid" in ch_id:
                        add_candidate(ch_id)
                    if ch_jid and "@" in ch_jid:
                        add_candidate(ch_jid)
                    if ch_id and "@" in ch_id:
                        add_candidate(ch_id)
        except Exception as exc:
            logger.debug("Failed checking chats for JID resolution: %s", exc)

        return candidates

    async def fetch_messages_by_number(
        self,
        instance_name: str,
        number: str,
        limit: int = 1000,
    ) -> list[dict]:
        """Fetch messages by phone number using Evolution API's built-in number filter.

        This is the most reliable approach — Evolution API filters server-side.
        Confirmed working via test_group_match.py scratch tests.
        """
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(
                    self._url(f"/chat/findMessages/{instance_name}"),
                    headers=self.headers,
                    json={"number": number, "limit": limit},
                )
                if resp.status_code == 200:
                    return self._parse_message_records(resp.json())
            except Exception as exc:
                logger.debug("fetch_messages_by_number failed for %s (number=%s): %s", instance_name, number, exc)
        return []

    async def fetch_messages(
        self,
        instance_name: str,
        remote_jid: str,
        count: int = 100,
    ) -> list[dict]:
        """Fetch historical messages from Evolution API for a specific JID.

        Uses where.key.remoteJid filter. Works best when the exact JID is known.
        """
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(
                    self._url(f"/chat/findMessages/{instance_name}"),
                    headers=self.headers,
                    json={
                        "where": {"key": {"remoteJid": remote_jid}},
                        "limit": count,
                    },
                )
                if resp.status_code == 200:
                    return self._parse_message_records(resp.json())
            except Exception as exc:
                logger.debug("fetch_messages by JID failed for %s (JID=%s): %s", instance_name, remote_jid, exc)
        return []

    async def fetch_messages_for_contact(self, instance_name: str, phone: str) -> list[dict]:
        """Fetch all historical messages for a specific phone number from Evolution API.

        Strategy (in priority order):
        1. number-param queries — Evolution API filters server-side. MOST RELIABLE.
           Confirmed working in scratch/test_group_match.py and scratch/test_fetch.py.
        2. JID-based queries — fallback if number-param returns nothing.
           Handles @lid privacy JIDs discovered via findContacts / findChats.

        The old 'broad page scan' approach was REMOVED because Evolution API does not
        reliably honour the `page` param, causing all pages to return the same 100 messages.
        """
        digits = re.sub(r"\D", "", str(phone or ""))
        if not digits:
            return []

        suffix10 = digits[-10:] if len(digits) >= 10 else digits
        clean_12 = f"91{suffix10}" if len(suffix10) == 10 else digits
        # Unique candidate numbers to query (preserve order, no duplicates)
        candidate_numbers: list[str] = list(dict.fromkeys(
            n for n in [clean_12, digits, suffix10] if n
        ))

        seen_msg_ids: set = set()
        matched: list[dict] = []

        def is_for_contact(m: dict) -> bool:
            """Check whether this message belongs to the target phone contact."""
            p = extract_contact_phone_from_message(m)
            if p:
                if p == clean_12 or p == digits:
                    return True
                if len(suffix10) >= 10 and (p.endswith(suffix10) or suffix10 in p):
                    return True
            # Fallback: check remoteJid / remoteJidAlt directly
            key_d = m.get("key", {}) if isinstance(m.get("key"), dict) else {}
            for field in [
                key_d.get("remoteJid"), key_d.get("remoteJidAlt"),
                m.get("remoteJid"), m.get("remoteJidAlt"),
            ]:
                if not field:
                    continue
                f_str = str(field)
                if "@g.us" in f_str or "@broadcast" in f_str:
                    continue
                user = f_str.split("@")[0].split(":")[0]
                user_digits = re.sub(r"\D", "", user)
                if len(suffix10) >= 10 and user_digits.endswith(suffix10):
                    return True
            return False

        def add_if_match(m: dict):
            if not isinstance(m, dict):
                return
            key_d = m.get("key", {}) if isinstance(m.get("key"), dict) else {}
            jid = str(key_d.get("remoteJid") or m.get("remoteJid") or "")
            if "@g.us" in jid or "@broadcast" in jid:
                return
            if not is_for_contact(m):
                return
            wa_id = key_d.get("id") or m.get("id")
            if wa_id and wa_id in seen_msg_ids:
                return
            if wa_id:
                seen_msg_ids.add(wa_id)
            matched.append(m)

        # ── Strategy 1: number-param (server-side filter by Evolution API) ──────────
        for num in candidate_numbers:
            records = await self.fetch_messages_by_number(instance_name, num)
            before = len(matched)
            for m in records:
                add_if_match(m)
            logger.info(
                "fetch_messages_for_contact: number=%s → %d raw records, %d new matched (total=%d)",
                num, len(records), len(matched) - before, len(matched)
            )

        # ── Strategy 2: JID-based (handles @lid privacy IDs) ─────────────────────
        if not matched:
            candidate_jids = await self.resolve_jids_for_phone(instance_name, phone)
            logger.info("Resolved JIDs for phone %s: %s", phone, candidate_jids)
            for jid in candidate_jids:
                records = await self.fetch_messages(instance_name, jid, count=100)
                before = len(matched)
                for m in records:
                    add_if_match(m)
                logger.info(
                    "fetch_messages_for_contact: JID=%s → %d raw records, %d new matched (total=%d)",
                    jid, len(records), len(matched) - before, len(matched)
                )

        logger.info("fetch_messages_for_contact: FINAL %d messages for phone=%s", len(matched), phone)
        return matched


# Singleton-ish — imported as `from app.services.whatsapp import evo_client`
evo_client = EvolutionAPIClient()


# ═══════════════════════════════════════════════════════════════════════
# Phone Extraction Helper
# ═══════════════════════════════════════════════════════════════════════

def extract_contact_phone_from_message(raw_msg: dict) -> str:
    """Extract the contact's phone digits from an Evolution API message record.

    Checks remoteJidAlt / participantAlt first (alternative JID fields that often
    contain the real phone number when the main JID is an @lid privacy identifier),
    then falls back to remoteJid and other fields.

    Returns only digit strings of length >= 10 to avoid matching short IDs.
    Skips group/broadcast JIDs.
    """
    if not isinstance(raw_msg, dict):
        return ""

    key = raw_msg.get("key", {}) if isinstance(raw_msg.get("key"), dict) else {}
    candidates = [
        key.get("remoteJidAlt"), key.get("participantAlt"),
        raw_msg.get("remoteJidAlt"), raw_msg.get("participantAlt"),
        key.get("remoteJid"), raw_msg.get("remoteJid"),
        raw_msg.get("chatId"), raw_msg.get("from"), raw_msg.get("to"),
    ]

    # First pass: skip group/broadcast/@lid JIDs
    for c in candidates:
        if not c:
            continue
        c_str = str(c)
        if "@g.us" in c_str or "@broadcast" in c_str or "@newsletter" in c_str or "@lid" in c_str:
            continue
        user_part = c_str.split("@")[0].split(":")[0]
        digits = re.sub(r"\D", "", user_part)
        if len(digits) >= 10:
            return digits

    # Second pass: accept non-group JIDs even if they don't have a long digit string
    for c in candidates:
        if c and "@g.us" not in str(c) and "@broadcast" not in str(c):
            user_part = str(c).split("@")[0].split(":")[0]
            digits = re.sub(r"\D", "", user_part)
            if digits:
                return digits
    return ""


# ═══════════════════════════════════════════════════════════════════════
# Message Processing Helpers
# ═══════════════════════════════════════════════════════════════════════

def extract_content_and_media(msg_obj: dict | None, top_level: dict | None = None) -> tuple[str, str | None]:
    """Extract readable text content and media type from Evolution API message payload."""
    if not msg_obj and isinstance(top_level, dict):
        msg_obj = top_level.get("message") or top_level

    if not isinstance(msg_obj, dict):
        return "", None

    # Unwrap ephemeral or viewOnce wrappers
    if "ephemeralMessage" in msg_obj and isinstance(msg_obj["ephemeralMessage"], dict):
        msg_obj = msg_obj["ephemeralMessage"].get("message", msg_obj["ephemeralMessage"])
    if "viewOnceMessage" in msg_obj and isinstance(msg_obj["viewOnceMessage"], dict):
        msg_obj = msg_obj["viewOnceMessage"].get("message", msg_obj["viewOnceMessage"])
    if "viewOnceMessageV2" in msg_obj and isinstance(msg_obj["viewOnceMessageV2"], dict):
        msg_obj = msg_obj["viewOnceMessageV2"].get("message", msg_obj["viewOnceMessageV2"])
    if "documentWithCaptionMessage" in msg_obj and isinstance(msg_obj["documentWithCaptionMessage"], dict):
        msg_obj = msg_obj["documentWithCaptionMessage"].get("message", msg_obj["documentWithCaptionMessage"])

    if not isinstance(msg_obj, dict):
        return "", None

    content = (
        msg_obj.get("conversation")
        or (msg_obj.get("extendedTextMessage", {}) if isinstance(msg_obj.get("extendedTextMessage"), dict) else {}).get("text")
        or ""
    )

    media_type = None
    if "imageMessage" in msg_obj and isinstance(msg_obj["imageMessage"], dict):
        media_type = "image"
        content = content or msg_obj["imageMessage"].get("caption", "[Image]")
    elif "videoMessage" in msg_obj and isinstance(msg_obj["videoMessage"], dict):
        media_type = "video"
        content = content or msg_obj["videoMessage"].get("caption", "[Video]")
    elif "audioMessage" in msg_obj:
        media_type = "audio"
        content = content or "[Voice Note]"
    elif "documentMessage" in msg_obj and isinstance(msg_obj["documentMessage"], dict):
        media_type = "document"
        content = content or msg_obj["documentMessage"].get("fileName", "[Document]")
    elif "contactMessage" in msg_obj:
        media_type = "contact"
        content = content or "[Contact Card]"
    elif "locationMessage" in msg_obj:
        media_type = "location"
        content = content or "[Location]"

    return content, media_type


def extract_timestamp(raw: dict) -> datetime:
    """Parse timestamp from Evolution API message record."""
    raw_ts = raw.get("messageTimestamp") or raw.get("timestamp")
    if raw_ts:
        try:
            return datetime.fromtimestamp(int(raw_ts), tz=timezone.utc)
        except (ValueError, TypeError, OverflowError):
            pass
    return datetime.now(timezone.utc)


def _normalise_phone(phone: str) -> str:
    """Strip +, spaces, dashes from a phone number for comparison."""
    if not phone: return ""
    return phone.replace("+", "").replace(" ", "").replace("-", "").strip()

def _normalise_phone_for_wa(phone: str) -> str:
    """Strip chars, and if it's exactly 10 digits, prepend '91'."""
    clean = _normalise_phone(phone)
    if len(clean) == 10 and clean.isdigit():
        return f"91{clean}"
    return clean

async def match_lead_by_phone(db: AsyncSession, phone: str) -> Lead | None:
    """Find a lead whose phone_number matches the given WhatsApp phone.

    Automatically handles cases where the CRM lead has a 10-digit number
    but WhatsApp sends it with the 91 country code.
    """
    from sqlalchemy import or_
    
    clean_wa = _normalise_phone_for_wa(phone)
    clean_lead = func.replace(func.replace(func.replace(Lead.phone_number, "+", ""), " ", ""), "-", "")
    
    result = await db.execute(
        select(Lead).where(
            or_(
                clean_lead == clean_wa,
                func.concat("91", clean_lead) == clean_wa,
                clean_lead == _normalise_phone(phone)
            )
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
    is_from_me: bool = False,
) -> WhatsAppMessage:
    """Process an inbound WhatsApp message from the Evolution API webhook.

    1. Match the correct phone number (sender if inbound, receiver if outbound) to a Lead.
    2. Find the assigned sales rep.
    3. Save the WhatsAppMessage row.
    4. Log a LeadTimeline entry for AI context.
    """
    # 1. Match lead
    lead_phone = receiver_phone if is_from_me else sender_phone
    lead = await match_lead_by_phone(db, lead_phone)
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
