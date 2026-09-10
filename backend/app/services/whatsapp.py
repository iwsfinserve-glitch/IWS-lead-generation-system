"""
WhatsApp Service — Evolution API client and message processing logic.

Handles:
1. HTTP communication with the self-hosted Evolution API instance.
2. Incoming message processing (webhook → upsert to DB → timeline/notification).
3. Outbound message sending via Evolution API.
4. History sync: fetch ALL messages for a contact from Evolution API and
   upsert only the ones that are not already in the DB (additive, never wipes).

Design principles (v3):
- upsert_message() is the SINGLE canonical save path for all WhatsApp messages.
- Sync is ADDITIVE: fetches everything from Evolution API, inserts only what's
  missing from our DB. No DELETE ever happens during sync.
- upsert_message() uses SQLAlchemy savepoints (begin_nested) instead of a full
  session rollback — so a duplicate-key IntegrityError on message N never wipes
  messages 1..(N-1) that were already added in the same batch.
- lead_id / user_id are resolved by the caller; upsert_message() accepts whatever
  it's given and saves regardless (no lead-match guard).
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
    """Thin wrapper around the Evolution API REST endpoints."""

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
        """Fetch the QR code for an instance waiting for scan."""
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
        We treat any response as success since the intent is achieved.
        """
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.delete(
                self._url(f"/instance/logout/{instance_name}"),
                headers=self.headers,
            )
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
        """Send a text message via the connected WhatsApp instance."""
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
        self, instance_name: str, number: str, limit: int = 1000
    ) -> list[dict]:
        """Fetch messages using Evolution API's number filter (server-side)."""
        async with httpx.AsyncClient(timeout=60) as client:
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
                    "_fetch_by_number failed (%s, number=%s): %s",
                    instance_name, number, exc,
                )
        return []

    async def _fetch_by_jid(
        self, instance_name: str, remote_jid: str, limit: int = 1000
    ) -> list[dict]:
        """Fetch messages using an exact WhatsApp JID (remoteJid filter)."""
        async with httpx.AsyncClient(timeout=60) as client:
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
                    "_fetch_by_jid failed (%s, jid=%s): %s",
                    instance_name, remote_jid, exc,
                )
        return []

    async def _fetch_broad(self, instance_name: str, limit: int = 2000) -> list[dict]:
        """Broad fetch — returns the N most recent messages across all chats.

        Used as a fallback when number/JID specific queries return nothing.
        Caller is responsible for filtering by phone.
        """
        async with httpx.AsyncClient(timeout=90) as client:
            try:
                resp = await client.post(
                    self._url(f"/chat/findMessages/{instance_name}"),
                    headers=self.headers,
                    json={"limit": limit},
                )
                if resp.status_code == 200:
                    records = self._parse_message_records(resp.json())
                    logger.info(
                        "_fetch_broad(%s, limit=%d): %d records",
                        instance_name, limit, len(records),
                    )
                    return records
            except Exception as exc:
                logger.warning("_fetch_broad failed for %s: %s", instance_name, exc)
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
        """Resolve all candidate WhatsApp JIDs for a phone number."""
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

                for jid_candidate in [c_lid, c_jid, c_id, c_alt]:
                    add(jid_candidate)
        except Exception as exc:
            logger.debug("_resolve_candidate_jids contacts failed: %s", exc)

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
            logger.debug("_resolve_candidate_jids chats failed: %s", exc)

        return candidates

    async def fetch_messages_for_contact(
        self,
        instance_name: str,
        phone: str,
        limit: int = 1000,
    ) -> list[dict]:
        """Fetch the complete conversation history for a phone number.

        Returns ALL messages — old and new, inbound and outbound — for this
        contact. Uses three strategies in order:

        1. Number-param filter (server-side, most reliable when it works)
        2. JID-targeted queries (handles @lid privacy identifiers)
        3. Broad fetch + client-side phone filter (fallback — always works)

        All results are merged and deduplicated by message ID before returning.
        """
        digits = re.sub(r"\D", "", str(phone or ""))
        if not digits:
            return []

        suffix10 = digits[-10:] if len(digits) >= 10 else digits
        clean_12 = f"91{suffix10}" if len(suffix10) == 10 else digits

        all_records: dict[str, dict] = {}

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
                    synthetic = f"__no_id_{len(all_records)}"
                    all_records[synthetic] = rec

        # ── Strategy 1: number-param filter ──────────────────────────
        for number in dict.fromkeys([clean_12, suffix10, digits]):
            if not number:
                continue
            records = await self._fetch_by_number(instance_name, number, limit=limit)
            before = len(all_records)
            merge(records)
            if len(all_records) > before:
                logger.info(
                    "fetch_messages_for_contact: number=%s → +%d records (phone=%s)",
                    number, len(all_records) - before, phone,
                )

        # ── Strategy 2: JID-targeted queries ─────────────────────────
        candidate_jids = await self._resolve_candidate_jids(instance_name, phone)
        for jid in candidate_jids:
            records = await self._fetch_by_jid(instance_name, jid, limit=limit)
            before = len(all_records)
            merge(records)
            if len(all_records) > before:
                logger.info(
                    "fetch_messages_for_contact: jid=%s → +%d records (phone=%s)",
                    jid, len(all_records) - before, phone,
                )

        # ── Strategy 3: broad fallback (if 1+2 returned nothing) ─────
        if not all_records:
            logger.info(
                "fetch_messages_for_contact: targeted queries returned 0 for phone=%s, "
                "falling back to broad fetch + client-side filter",
                phone,
            )
            raw_all = await self._fetch_broad(instance_name, limit=2000)
            for rec in raw_all:
                if not isinstance(rec, dict):
                    continue
                key_d = rec.get("key", {}) if isinstance(rec.get("key"), dict) else {}
                jid = str(key_d.get("remoteJid") or rec.get("remoteJid") or "")
                # Skip groups
                if "@g.us" in jid or "@broadcast" in jid:
                    continue
                # Client-side match by last-10 digits
                jid_digits = re.sub(r"\D", "", jid.split("@")[0].split(":")[0])
                if not jid_digits:
                    continue
                if not (
                    suffix10 in jid_digits
                    or (len(jid_digits) >= 10 and jid_digits[-10:] == suffix10)
                ):
                    continue
                msg_id = key_d.get("id") or rec.get("id")
                if msg_id:
                    if msg_id not in all_records:
                        all_records[msg_id] = rec
                else:
                    all_records[f"__no_id_{len(all_records)}"] = rec

            if all_records:
                logger.info(
                    "fetch_messages_for_contact: broad fallback found %d records for phone=%s",
                    len(all_records), phone,
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
    """Find a lead whose phone_number matches the given WhatsApp phone."""
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

    IMPORTANT — transaction safety:
    On IntegrityError (duplicate whatsapp_msg_id race condition), this function
    uses a SQLAlchemy savepoint (begin_nested) so that only the failing INSERT
    is rolled back. The outer transaction — and all other messages inserted in
    the same batch — remains intact. This prevents a single duplicate from
    wiping an entire sync batch.

    Returns:
        (WhatsAppMessage, is_new: bool)
        is_new=True  → message was newly inserted
        is_new=False → message already existed (no DB change)
    """
    # Fast-path: check existence first to avoid hitting the savepoint on every message
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

    # Use a savepoint so that IntegrityError only rolls back THIS insert,
    # not the entire parent transaction / batch.
    try:
        async with db.begin_nested():
            db.add(msg)
            await db.flush()
    except IntegrityError:
        # Duplicate — fetch and return the existing row
        existing = await db.execute(
            select(WhatsAppMessage).where(
                WhatsAppMessage.whatsapp_msg_id == whatsapp_msg_id
            )
        )
        existing_msg = existing.scalar_one_or_none()
        return (existing_msg or msg), False

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
    """Process an inbound WhatsApp message event from the Evolution API webhook."""
    lead_phone = receiver_phone if is_from_me else sender_phone
    lead = await match_lead_by_phone(db, lead_phone)
    lead_id = lead.id if lead else None
    user_id = lead.assigned_rep_id if lead else None

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

    if lead_id and user_id:
        preview = (content or "")[:200]
        db.add(LeadTimeline(
            lead_id=lead_id,
            user_id=user_id,
            event_type="whatsapp_message",
            event_metadata={
                "direction": "outbound" if is_from_me else "inbound",
                "sender_phone": sender_phone,
                "content_preview": preview,
                "media_type": media_type,
            },
        ))

        if not is_from_me:
            lead_display = lead.name if lead else sender_phone
            db.add(Notification(
                user_id=user_id,
                title=f"WhatsApp from {lead_display}",
                message=preview or "[Media]",
                notification_type="whatsapp_message",
                link_type="lead",
                link_id=lead_id,
            ))

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
    """Save an outbound message sent from the CRM and log it to the timeline."""
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
        db.add(LeadTimeline(
            lead_id=lead_id,
            user_id=user_id,
            event_type="whatsapp_message",
            event_metadata={
                "direction": "outbound",
                "receiver_phone": receiver_phone,
                "content_preview": content[:200],
            },
        ))

    await db.commit()
    await db.refresh(msg)
    return msg
