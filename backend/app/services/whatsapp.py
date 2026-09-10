"""
WhatsApp Service — Evolution API client and message processing logic.

Handles:
1. HTTP communication with the self-hosted Evolution API instance.
2. Incoming message processing (webhook → upsert to DB → timeline/notification).
3. Outbound message sending via Evolution API.
4. History sync: fetch ALL messages for a contact from Evolution API and
   upsert only the ones that are not already in the DB (additive, never wipes).

The Evolution API runs as a sibling Railway service and exposes a REST API
authenticated by a global API key.

Design principles (v2):
- upsert_message() is the SINGLE canonical save path — both the webhook and
  the manual sync funnel through here.
- Sync is ADDITIVE: old messages, new messages, inbound and outbound are all
  fetched from Evolution API. Only messages whose whatsapp_msg_id does not
  yet exist in the DB are inserted.
- No DELETE ever happens during a sync. Pressing sync is always safe.
- lead_id / user_id are resolved by the caller; upsert_message() does not do
  phone matching — it accepts whatever it's given.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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

    # ── Instance Management ────────────────────────────────────────────

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
            data = resp.json()

        # Ensure syncFullHistory is enabled for complete message history
        try:
            await self.set_instance_settings(instance_name, {"syncFullHistory": True})
        except Exception as exc:
            logger.debug("Failed to enable syncFullHistory on create for %s: %s", instance_name, exc)

        return data

    async def set_instance_settings(self, instance_name: str, settings_dict: dict) -> dict:
        """Update settings for an Evolution instance (e.g. syncFullHistory)."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                self._url(f"/settings/set/{instance_name}"),
                headers=self.headers,
                json=settings_dict,
            )
            if resp.status_code == 200:
                return resp.json()
        return {}

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

    async def logout_instance(self, instance_name: str) -> dict:
        """Disconnect (logout) an instance without deleting it.

        Evolution API often returns 4xx/5xx even on a successful logout
        (e.g. 400 if already disconnected, 404 if session not found).
        We treat any response as success since the intent is achieved —
        the session is disconnected regardless of the status code.
        """
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.delete(
                self._url(f"/instance/logout/{instance_name}"),
                headers=self.headers,
            )
            # Don't raise — Evolution API frequently returns non-200 on logout
            # even when the disconnection actually succeeds.
            try:
                return resp.json()
            except Exception:
                return {"status": "disconnected", "http_status": resp.status_code}

    async def list_instances(self) -> list[dict]:
        """List all registered instances."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                self._url("/instance/fetchInstances"),
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()

    # ── Messaging ──────────────────────────────────────────────────────

    async def send_text_message(self, instance_name: str, phone: str, text: str) -> dict:
        """Send a text message via the connected WhatsApp instance.

        Args:
            instance_name: The Evolution API session name.
            phone: Recipient phone in international format (e.g. '919876543210').
            text: Message text content.
        """
        clean_phone = phone.replace("+", "").replace(" ", "").replace("-", "")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self._url(f"/message/sendText/{instance_name}"),
                headers=self.headers,
                json={"number": clean_phone, "text": text},
            )
            resp.raise_for_status()
            return resp.json()

    # ── Message Fetching ───────────────────────────────────────────────

    def _parse_message_records(self, data) -> list[dict]:
        """Parse Evolution API findMessages response into a flat list of records."""
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

    async def _fetch_by_number(
        self,
        instance_name: str,
        number: str,
        limit: int = 1000,
    ) -> list[dict]:
        """Fetch messages using Evolution API's built-in number filter.

        This is the most reliable approach — server-side filtering by phone number.
        Returns all messages (inbound + outbound) for that contact.
        """
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(
                    self._url(f"/chat/findMessages/{instance_name}"),
                    headers=self.headers,
                    json={"number": number, "limit": limit},
                )
                if resp.status_code == 200:
                    records = self._parse_message_records(resp.json())
                    logger.debug(
                        "_fetch_by_number(%s, number=%s): %d records",
                        instance_name, number, len(records),
                    )
                    return records
            except Exception as exc:
                logger.debug(
                    "_fetch_by_number failed for %s (number=%s): %s",
                    instance_name, number, exc,
                )
        return []

    async def _fetch_by_jid(
        self,
        instance_name: str,
        remote_jid: str,
        limit: int = 1000,
    ) -> list[dict]:
        """Fetch messages using a specific WhatsApp JID (remoteJid filter).

        Used as a supplementary strategy when the exact JID is known
        (including @lid privacy-identifier JIDs).
        """
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(
                    self._url(f"/chat/findMessages/{instance_name}"),
                    headers=self.headers,
                    json={
                        "where": {"key": {"remoteJid": remote_jid}},
                        "limit": limit,
                    },
                )
                if resp.status_code == 200:
                    records = self._parse_message_records(resp.json())
                    logger.debug(
                        "_fetch_by_jid(%s, jid=%s): %d records",
                        instance_name, remote_jid, len(records),
                    )
                    return records
            except Exception as exc:
                logger.debug(
                    "_fetch_by_jid failed for %s (jid=%s): %s",
                    instance_name, remote_jid, exc,
                )
        return []

    async def find_contacts(self, instance_name: str) -> list[dict]:
        """Fetch all contacts for an instance from Evolution API."""
        async with httpx.AsyncClient(timeout=20) as client:
            for method in ["POST", "GET"]:
                try:
                    if method == "POST":
                        resp = await client.post(
                            self._url(f"/chat/findContacts/{instance_name}"),
                            headers=self.headers,
                            json={},
                        )
                    else:
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
                    logger.debug("findContacts %s failed for %s: %s", method, instance_name, exc)
            return []

    async def find_chats(self, instance_name: str) -> list[dict]:
        """Fetch all chats for an instance from Evolution API."""
        async with httpx.AsyncClient(timeout=20) as client:
            for method in ["POST", "GET"]:
                try:
                    if method == "POST":
                        resp = await client.post(
                            self._url(f"/chat/findChats/{instance_name}"),
                            headers=self.headers,
                            json={},
                        )
                    else:
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
                    logger.debug("findChats %s failed for %s: %s", method, instance_name, exc)
            return []

    async def _resolve_candidate_jids(self, instance_name: str, phone: str) -> list[str]:
        """Resolve all candidate WhatsApp JIDs for a phone number.

        Builds the standard @s.whatsapp.net JIDs plus queries contacts/chats
        to discover any @lid privacy-identifier JIDs for this contact.
        Returns a deduplicated, ordered list of JIDs to try.
        """
        digits = re.sub(r"\D", "", str(phone or ""))
        if not digits:
            return []

        candidates: list[str] = []
        seen: set[str] = set()

        def add(jid: str | None):
            if not jid or not isinstance(jid, str):
                return
            jid = jid.strip()
            if not jid or "@g.us" in jid or "@broadcast" in jid:
                return
            if jid not in seen:
                seen.add(jid)
                candidates.append(jid)

        # Standard JID formats
        clean_wa = _normalise_phone_for_wa(phone)
        if clean_wa:
            add(f"{clean_wa}@s.whatsapp.net")
        if digits != clean_wa:
            add(f"{digits}@s.whatsapp.net")
        if len(digits) == 10:
            add(f"91{digits}@s.whatsapp.net")
        elif digits.startswith("91") and len(digits) > 10:
            add(f"{digits[2:]}@s.whatsapp.net")

        last10 = digits[-10:] if len(digits) >= 10 else digits

        # Check contacts for @lid or alternative JIDs
        try:
            contacts = await self.find_contacts(instance_name)
            for c in contacts:
                if not isinstance(c, dict):
                    continue
                c_id = str(c.get("id") or "")
                c_jid = str(c.get("remoteJid") or "")
                c_lid = str(c.get("lid") or "")
                c_alt = str(c.get("remoteJidAlt") or "")
                c_num = str(c.get("number") or c.get("phoneNumber") or "")

                if not (
                    (last10 and (last10 in c_id or last10 in c_jid or last10 in c_num))
                    or (digits and (digits in c_id or digits in c_jid or digits in c_num))
                ):
                    continue

                # Prefer @lid first (most specific), then standard JIDs
                for jid_candidate in [c_lid, c_jid, c_id, c_alt]:
                    add(jid_candidate)
        except Exception as exc:
            logger.debug("_resolve_candidate_jids contacts check failed: %s", exc)

        # Also check active chats
        try:
            chats = await self.find_chats(instance_name)
            for ch in chats:
                if not isinstance(ch, dict):
                    continue
                ch_id = str(ch.get("id") or "")
                ch_jid = str(ch.get("remoteJid") or "")
                ch_lid = str(ch.get("lid") or "")
                ch_phone = str(ch.get("phone") or "")

                if not (
                    (last10 and (last10 in ch_id or last10 in ch_jid or last10 in ch_phone))
                    or (digits and (digits in ch_id or digits in ch_jid or digits in ch_phone))
                ):
                    continue

                for jid_candidate in [ch_lid, ch_jid, ch_id]:
                    add(jid_candidate)
        except Exception as exc:
            logger.debug("_resolve_candidate_jids chats check failed: %s", exc)

        return candidates

    async def fetch_messages_for_contact(
        self,
        instance_name: str,
        phone: str,
        limit: int = 1000,
    ) -> list[dict]:
        """Fetch the complete conversation history for a phone number.

        Returns ALL messages — old and new, inbound and outbound — for this
        contact from Evolution API's local database. Deduplication by
        whatsapp_msg_id is the caller's responsibility.

        Strategy:
        1. Primary: number-param filter (confirmed working, server-side filter).
           Tries the 12-digit (with country code) and 10-digit variants.
        2. Supplementary: JID-targeted queries for each resolved JID.
           Catches @lid contacts and any JID the number-filter missed.

        All results are merged and deduplicated by message ID before returning.
        """
        digits = re.sub(r"\D", "", str(phone or ""))
        if not digits:
            return []

        suffix10 = digits[-10:] if len(digits) >= 10 else digits
        clean_12 = f"91{suffix10}" if len(suffix10) == 10 else digits

        # Collect all records, dedup by message ID
        all_records: dict[str, dict] = {}  # msg_id → record

        def merge(records: list[dict]):
            for rec in records:
                if not isinstance(rec, dict):
                    continue
                key_d = rec.get("key", {}) if isinstance(rec.get("key"), dict) else {}
                msg_id = key_d.get("id") or rec.get("id")
                if msg_id:
                    if msg_id not in all_records:
                        all_records[msg_id] = rec
                else:
                    # No ID — use a synthetic key to avoid dropping the record
                    ts = rec.get("messageTimestamp") or rec.get("timestamp") or "0"
                    synthetic = f"__no_id_{ts}_{len(all_records)}"
                    all_records[synthetic] = rec

        # ── Strategy 1: number-param fetch (primary) ──────────────────
        for number in dict.fromkeys([clean_12, suffix10, digits]):
            if not number:
                continue
            records = await self._fetch_by_number(instance_name, number, limit=limit)
            before = len(all_records)
            merge(records)
            added = len(all_records) - before
            if added:
                logger.info(
                    "fetch_messages_for_contact: number=%s contributed %d records for phone=%s",
                    number, added, phone,
                )

        # ── Strategy 2: JID-targeted queries (supplementary) ─────────
        candidate_jids = await self._resolve_candidate_jids(instance_name, phone)
        for jid in candidate_jids:
            records = await self._fetch_by_jid(instance_name, jid, limit=limit)
            before = len(all_records)
            merge(records)
            added = len(all_records) - before
            if added:
                logger.info(
                    "fetch_messages_for_contact: jid=%s contributed %d new records for phone=%s",
                    jid, added, phone,
                )

        result = list(all_records.values())
        logger.info(
            "fetch_messages_for_contact: TOTAL %d records for phone=%s (instance=%s)",
            len(result), phone, instance_name,
        )
        return result


# Singleton — imported as `from app.services.whatsapp import evo_client`
evo_client = EvolutionAPIClient()


# ═══════════════════════════════════════════════════════════════════════
# Phone Normalisation Helpers
# ═══════════════════════════════════════════════════════════════════════

def _normalise_phone(phone: str) -> str:
    """Strip +, spaces, dashes from a phone number."""
    if not phone:
        return ""
    return phone.replace("+", "").replace(" ", "").replace("-", "").strip()


def _normalise_phone_for_wa(phone: str) -> str:
    """Strip non-digits and, if exactly 10 digits, prepend '91' (India)."""
    clean = _normalise_phone(phone)
    if len(clean) == 10 and clean.isdigit():
        return f"91{clean}"
    return clean


# ═══════════════════════════════════════════════════════════════════════
# Message Content / Timestamp Extraction
# ═══════════════════════════════════════════════════════════════════════

def extract_content_and_media(
    msg_obj: dict | None,
    top_level: dict | None = None,
) -> tuple[str, str | None]:
    """Extract readable text content and media type from an Evolution API message payload."""
    if not msg_obj and isinstance(top_level, dict):
        msg_obj = top_level.get("message") or top_level

    if not isinstance(msg_obj, dict):
        return "", None

    # Unwrap message wrappers
    for wrapper_key in (
        "ephemeralMessage",
        "viewOnceMessage",
        "viewOnceMessageV2",
        "documentWithCaptionMessage",
    ):
        if wrapper_key in msg_obj and isinstance(msg_obj[wrapper_key], dict):
            inner = msg_obj[wrapper_key]
            msg_obj = inner.get("message", inner)

    if not isinstance(msg_obj, dict):
        return "", None

    content = (
        msg_obj.get("conversation")
        or (
            (msg_obj.get("extendedTextMessage") or {}).get("text")
            if isinstance(msg_obj.get("extendedTextMessage"), dict)
            else None
        )
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
    elif "stickerMessage" in msg_obj:
        media_type = "sticker"
        content = content or "[Sticker]"

    return content, media_type


def extract_timestamp(raw: dict) -> datetime:
    """Parse timestamp from an Evolution API message record."""
    raw_ts = raw.get("messageTimestamp") or raw.get("timestamp")
    if raw_ts:
        try:
            return datetime.fromtimestamp(int(raw_ts), tz=timezone.utc)
        except (ValueError, TypeError, OverflowError):
            pass
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════
# Lead Matching
# ═══════════════════════════════════════════════════════════════════════

async def match_lead_by_phone(db: AsyncSession, phone: str) -> Lead | None:
    """Find a lead whose phone_number matches the given WhatsApp phone.

    Handles 10-digit vs 12-digit (with country code 91) mismatches automatically.
    """
    from sqlalchemy import func, or_

    clean_wa = _normalise_phone_for_wa(phone)
    clean_lead = func.replace(
        func.replace(func.replace(Lead.phone_number, "+", ""), " ", ""), "-", ""
    )

    result = await db.execute(
        select(Lead).where(
            or_(
                clean_lead == clean_wa,
                func.concat("91", clean_lead) == clean_wa,
                clean_lead == _normalise_phone(phone),
            )
        )
    )
    return result.scalar_one_or_none()


# ═══════════════════════════════════════════════════════════════════════
# Canonical Save Path: upsert_message()
# ═══════════════════════════════════════════════════════════════════════

async def upsert_message(
    db: AsyncSession,
    *,
    lead_id: int | None,
    user_id: int | None,
    instance_name: str,
    sender_phone: str,
    receiver_phone: str,
    direction: MessageDirection,
    content: str | None,
    whatsapp_msg_id: str | None,
    media_type: str | None = None,
    media_url: str | None = None,
    status: MessageStatus = MessageStatus.delivered,
    timestamp: datetime | None = None,
) -> Tuple[WhatsAppMessage, bool]:
    """Insert a WhatsApp message if it doesn't already exist; skip if it does.

    This is the SINGLE canonical save path for all WhatsApp messages — both
    the real-time webhook and the manual sync endpoint use this function.

    Args:
        db: Database session.
        lead_id: CRM lead to associate with (None if unknown).
        user_id: Sales rep user ID (None if unknown).
        instance_name: Evolution API instance name (e.g. 'rep_5').
        sender_phone: Phone of the message sender.
        receiver_phone: Phone of the message receiver.
        direction: MessageDirection.inbound or .outbound.
        content: Text content of the message.
        whatsapp_msg_id: WhatsApp's own unique message ID (used for dedup).
        media_type: 'image' | 'video' | 'audio' | 'document' | None for text.
        media_url: URL to media file (if applicable).
        status: MessageStatus (default: delivered).
        timestamp: Message timestamp (default: now).

    Returns:
        Tuple of (WhatsAppMessage, is_new: bool).
        is_new=True means the message was newly inserted.
        is_new=False means it already existed (no DB change made).
    """
    # Check if already in DB by whatsapp_msg_id
    if whatsapp_msg_id:
        existing = await db.execute(
            select(WhatsAppMessage).where(
                WhatsAppMessage.whatsapp_msg_id == whatsapp_msg_id
            )
        )
        existing_msg = existing.scalar_one_or_none()
        if existing_msg is not None:
            return existing_msg, False

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
        status=status,
        timestamp=timestamp or datetime.now(timezone.utc),
    )
    db.add(msg)

    try:
        await db.flush()  # Flush to catch unique constraint violations early
    except IntegrityError:
        # Race condition: another request inserted the same message_id concurrently
        await db.rollback()
        existing = await db.execute(
            select(WhatsAppMessage).where(
                WhatsAppMessage.whatsapp_msg_id == whatsapp_msg_id
            )
        )
        existing_msg = existing.scalar_one_or_none()
        return existing_msg, False

    return msg, True


# ═══════════════════════════════════════════════════════════════════════
# Webhook Incoming Message Processing
# ═══════════════════════════════════════════════════════════════════════

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
    """Process an inbound WhatsApp message event from the Evolution API webhook.

    Steps:
    1. Determine which phone belongs to the lead (sender if inbound, receiver if outbound).
    2. Match the lead by phone number (best-effort; lead_id can be None).
    3. Upsert the message (skipped silently if already in DB).
    4. Log a LeadTimeline entry and create an in-app Notification (if matched to a lead).
    5. Commit.
    """
    # 1. Resolve lead
    lead_phone = receiver_phone if is_from_me else sender_phone
    lead = await match_lead_by_phone(db, lead_phone)
    lead_id = lead.id if lead else None
    user_id = lead.assigned_rep_id if lead else None

    # 2. Upsert message — no lead match guard, save regardless
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
        status=MessageStatus.delivered,
        timestamp=timestamp,
    )

    if not is_new:
        logger.debug("process_incoming_message: duplicate msg %s, skipping timeline", whatsapp_msg_id)
        await db.commit()
        return msg

    # 3. LeadTimeline + Notification (only when matched to a lead)
    if lead_id and user_id:
        preview = (content or "")[:200]
        timeline_entry = LeadTimeline(
            lead_id=lead_id,
            user_id=user_id,
            event_type="whatsapp_message",
            event_metadata={
                "direction": "outbound" if is_from_me else "inbound",
                "sender_phone": sender_phone,
                "content_preview": preview,
                "media_type": media_type,
            },
        )
        db.add(timeline_entry)

        # Notify the rep only for inbound messages
        if not is_from_me:
            lead_display = lead.name if lead else sender_phone
            notif = Notification(
                user_id=user_id,
                title=f"WhatsApp from {lead_display}",
                message=preview or "[Media]",
                notification_type="whatsapp_message",
                link_type="lead",
                link_id=lead_id,
            )
            db.add(notif)

    await db.commit()
    await db.refresh(msg)
    return msg


# ═══════════════════════════════════════════════════════════════════════
# Outbound Message Save (CRM-initiated sends)
# ═══════════════════════════════════════════════════════════════════════

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
    """Save an outbound message sent from the CRM and log it to the timeline.

    Always uses upsert_message() so duplicate webhook echoes are handled safely.
    """
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
        status=MessageStatus.sent,
        timestamp=datetime.now(timezone.utc),
    )

    if is_new:
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
