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
                    "syncFullHistory": True,
                    "groupsIgnore": True,
                    "alwaysOnline": True,
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
        # Normalise phone
        clean_phone = _normalise_phone_for_wa(phone)

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
        """Fetch historical messages from Evolution API for a specific chat or contact.

        Uses multiple fallback strategies to guarantee compatibility across
        different Evolution API versions, database backends (TypeORM / Postgres vs MongoDB),
        and WhatsApp JID variations (with/without country code, @lid, etc.):
        1. Targeted findMessages with candidate JIDs and query shapes (nested vs flat where).
        2. Lookup contact in findChats to discover their exact Evolution API JID/LID.
        3. Fetch recent instance messages and apply client-side filtering.
        4. Fallback to lastMessage from findChats.
        """
        raw_phone = phone_or_jid.split("@")[0] if "@" in phone_or_jid else phone_or_jid
        clean_phone = _normalise_phone_for_wa(raw_phone)
        digits = _extract_digits(raw_phone)
        suffix10 = digits[-10:] if len(digits) >= 10 else digits

        candidate_jids = []
        if "@" in phone_or_jid:
            candidate_jids.append(phone_or_jid)
        if clean_phone:
            candidate_jids.append(f"{clean_phone}@s.whatsapp.net")
        if suffix10 and suffix10 != clean_phone:
            candidate_jids.append(f"{suffix10}@s.whatsapp.net")

        # Deduplicate preserving order
        seen_jids = set()
        unique_candidate_jids = []
        for j in candidate_jids:
            if j not in seen_jids:
                seen_jids.add(j)
                unique_candidate_jids.append(j)

        def _parse_records(data) -> list[dict]:
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
            if isinstance(data, dict):
                msgs = data.get("messages")
                if isinstance(msgs, dict):
                    records = msgs.get("records") or msgs.get("rows") or msgs.get("data")
                    if isinstance(records, list):
                        return [item for item in records if isinstance(item, dict)]
                elif isinstance(msgs, list):
                    return [item for item in msgs if isinstance(item, dict)]
                for key in ["records", "data", "rows", "items", "result"]:
                    val = data.get(key)
                    if isinstance(val, list):
                        return [item for item in val if isinstance(item, dict)]
            return []

        async with httpx.AsyncClient(timeout=30) as client:
            # ── Strategy 1: Targeted findMessages with candidate JIDs & query shapes ──
            for c_jid in unique_candidate_jids:
                payloads = [
                    {"where": {"key": {"remoteJid": c_jid}}, "limit": count},
                    {"where": {"remoteJid": c_jid}, "limit": count},
                    {"where": {"key.remoteJid": c_jid}, "limit": count},
                ]
                for p in payloads:
                    try:
                        resp = await client.post(
                            self._url(f"/chat/findMessages/{instance_name}"),
                            headers=self.headers,
                            json=p,
                        )
                        if resp.status_code == 200:
                            records = _parse_records(resp.json())
                            if records:
                                logger.info(
                                    "fetch_messages: Found %d messages for %s using payload %s",
                                    len(records), c_jid, list(p["where"].keys())[0]
                                )
                                return records
                    except Exception as e:
                        logger.debug("Strategy 1 query failed for %s (%s): %s", c_jid, p, e)

            # ── Strategy 2: Check findChats to discover actual chat remoteJid / LID ──
            discovered_jid = None
            last_msg_fallback = None
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
                        if not isinstance(ch, dict):
                            continue
                        ch_jid = ch.get("remoteJid") or ch.get("id") or ch.get("jid") or ""
                        ch_digits = _extract_digits(str(ch_jid).split("@")[0])
                        ch_phone = _extract_digits(ch.get("phone") or ch.get("phoneNumber") or "")

                        if (suffix10 and (suffix10 in ch_digits or suffix10 in ch_phone)) or (clean_phone and clean_phone in ch_digits):
                            discovered_jid = ch_jid
                            if ch.get("lastMessage"):
                                last_msg_fallback = ch["lastMessage"]
                            break

                if discovered_jid and discovered_jid not in seen_jids:
                    for p in [
                        {"where": {"key": {"remoteJid": discovered_jid}}, "limit": count},
                        {"where": {"remoteJid": discovered_jid}, "limit": count},
                    ]:
                        try:
                            resp = await client.post(
                                self._url(f"/chat/findMessages/{instance_name}"),
                                headers=self.headers,
                                json=p,
                            )
                            if resp.status_code == 200:
                                records = _parse_records(resp.json())
                                if records:
                                    logger.info(
                                        "fetch_messages: Found %d messages for discovered JID %s",
                                        len(records), discovered_jid
                                    )
                                    return records
                        except Exception as e:
                            logger.debug("Strategy 2 query failed for %s: %s", discovered_jid, e)
            except Exception as e:
                logger.debug("Strategy 2 findChats failed: %s", e)

            # ── Strategy 3: Client-side filtering of recent messages ──
            try:
                resp = await client.post(
                    self._url(f"/chat/findMessages/{instance_name}"),
                    headers=self.headers,
                    json={"limit": 100},
                )
                if resp.status_code == 200:
                    all_records = _parse_records(resp.json())
                    filtered = []
                    for r in all_records:
                        if not isinstance(r, dict):
                            continue
                        r_key = r.get("key", {}) if isinstance(r.get("key"), dict) else {}
                        r_jid = r_key.get("remoteJid") or r.get("remoteJid") or ""
                        r_part = r_key.get("participant") or r.get("participant") or ""
                        r_digits = _extract_digits(str(r_jid).split("@")[0])
                        r_part_digits = _extract_digits(str(r_part).split("@")[0])

                        if suffix10 and (suffix10 in r_digits or suffix10 in r_part_digits):
                            filtered.append(r)
                        elif clean_phone and (clean_phone in r_digits or clean_phone in r_part_digits):
                            filtered.append(r)
                        elif discovered_jid and (discovered_jid == r_jid or discovered_jid == r_part):
                            filtered.append(r)

                    if filtered:
                        logger.info(
                            "fetch_messages: Client-side filter found %d messages for suffix %s",
                            len(filtered), suffix10
                        )
                        return filtered
            except Exception as e:
                logger.debug("Strategy 3 client-side filter failed: %s", e)

            # ── Strategy 4: Fallback to lastMessage from findChats ──
            if last_msg_fallback and isinstance(last_msg_fallback, dict):
                logger.info("fetch_messages: Falling back to lastMessage from findChats for %s", suffix10)
                return [last_msg_fallback]

            return []


# Singleton-ish — imported as `from app.services.whatsapp import evo_client`
evo_client = EvolutionAPIClient()


# ═══════════════════════════════════════════════════════════════════════
# Message Processing
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
    # 11 digits starting with 0 (e.g. 09876543210 -> 919876543210)
    if len(digits) == 11 and digits.startswith("0"):
        return f"91{digits[1:]}"
    # 10 digits Indian mobile number
    if len(digits) == 10:
        return f"91{digits}"
    # 12 digits starting with 91
    if len(digits) == 12 and digits.startswith("91"):
        return digits
    # Starting with 00 (e.g. 0091...)
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


async def match_lead_by_phone(db: AsyncSession, phone: str, assigned_rep_id: int | None = None) -> Lead | None:
    """Find a lead whose phone_number matches the given WhatsApp phone.
    Automatically handles cases where the CRM lead has formatted numbers,
    parentheses, leading 0, or 10-digit number with 91 WhatsApp country code.
    """
    from sqlalchemy import or_

    digits = _extract_digits(phone)
    if not digits:
        return None

    clean_wa = _normalise_phone_for_wa(phone)
    suffix10 = digits[-10:] if len(digits) >= 10 else digits

    # Clean Lead.phone_number in SQL: strip +, space, -, (, )
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
