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
# Phone Extraction & JID Normalization Helpers
# ═══════════════════════════════════════════════════════════════════════

def extract_contact_phone_from_message(raw_msg: dict) -> str:
    """Extract real phone number (international digits) from a WhatsApp/Evolution message dict.

    Handles standard JIDs (@s.whatsapp.net), multi-device JIDs (:0),
    and WhatsApp Privacy LIDs (@lid) with remoteJidAlt / participantAlt.
    """
    import re

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
    ]

    # Priority 1: Pick non-lid, non-group phone strings
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

    # Priority 2: Fallback to any digits if no standard @s.whatsapp.net found
    for c in candidates:
        if c and "@g.us" not in str(c) and "@broadcast" not in str(c):
            user_part = str(c).split("@")[0].split(":")[0]
            digits = re.sub(r"\D", "", user_part)
            if digits:
                return digits
    return ""


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
        """Check the connection status of an instance.
        
        If direct check returns 404/close, falls back to checking if any active
        instance is open in Evolution API.
        """
        async with httpx.AsyncClient(timeout=15) as client:
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
                logger.debug("get_instance_status direct check failed: %s", e)

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
                logger.debug("get_instance_status fallback check failed: %s", e)

            return {"instance": {"instanceName": instance_name, "state": "close"}}

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

        If target instance_name fails/404s, automatically falls back to an open instance.
        """
        clean_phone = phone.replace("+", "").replace(" ", "").replace("-", "")

        async with httpx.AsyncClient(timeout=30) as client:
            # First try requested instance
            try:
                resp = await client.post(
                    self._url(f"/message/sendText/{instance_name}"),
                    headers=self.headers,
                    json={
                        "number": clean_phone,
                        "text": text,
                    },
                )
                if resp.status_code in (200, 201):
                    return resp.json()
            except Exception as e:
                logger.warning("send_text_message via %s failed: %s", instance_name, e)

            # Fallback to any open instance
            try:
                list_resp = await client.get(self._url("/instance/fetchInstances"), headers=self.headers)
                if list_resp.status_code == 200:
                    instances = list_resp.json() if isinstance(list_resp.json(), list) else []
                    for inst in instances:
                        if inst.get("connectionStatus") == "open" and inst.get("name") != instance_name:
                            fallback_name = inst.get("name")
                            resp = await client.post(
                                self._url(f"/message/sendText/{fallback_name}"),
                                headers=self.headers,
                                json={"number": clean_phone, "text": text},
                            )
                            if resp.status_code in (200, 201):
                                logger.info("send_text_message succeeded via fallback instance %s", fallback_name)
                                return resp.json()
            except Exception as e:
                logger.error("send_text_message all fallbacks failed: %s", e)

            raise httpx.HTTPStatusError("No connected WhatsApp instance available to send message", request=None, response=None)

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
        """Deeply search and extract a list of message dicts from any Evolution API response format."""
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        
        if not isinstance(data, dict):
            return []

        # Check top-level keys first
        for key in ["messages", "records", "data", "rows", "items", "response", "result", "chats", "findMessages"]:
            val = data.get(key)
            if isinstance(val, list) and val and isinstance(val[0], dict):
                return val
            if isinstance(val, dict):
                for subkey in ["records", "rows", "data", "messages", "items", "response", "result"]:
                    inner = val.get(subkey)
                    if isinstance(inner, list) and inner and isinstance(inner[0], dict):
                        return inner

        # If still empty, recursively search dict for the first list of dicts that looks like messages
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                if any("key" in d or "message" in d or "id" in d or "body" in d or "remoteJid" in d for d in v[:3]):
                    return v
            elif isinstance(v, dict):
                found = EvolutionAPIClient._parse_message_response(v)
                if found:
                    return found
        return []

    async def fetch_messages(
        self,
        instance_name: str,
        phone: str,
        count: int = 100,
    ) -> list[dict]:
        """Fetch message history from Evolution API for a specific contact.

        Supports multi-instance auto-discovery, @lid Privacy JIDs (remoteJidAlt/participantAlt),
        multi-device JIDs (:0), where queries, and batch client-side filtering.
        """
        import re

        digits = re.sub(r"\D", "", str(phone or ""))
        if not digits:
            return []

        suffix10 = digits[-10:] if len(digits) >= 10 else digits
        clean_12 = f"91{suffix10}" if len(suffix10) == 10 else digits

        candidate_numbers = list(dict.fromkeys([clean_12, digits, suffix10]))
        candidate_jids = list(dict.fromkeys([
            f"{clean_12}@s.whatsapp.net",
            f"{digits}@s.whatsapp.net",
            f"{suffix10}@s.whatsapp.net",
        ]))

        def _is_chat_message(m: dict) -> bool:
            """Check if a message dict strictly belongs to this lead contact."""
            if not isinstance(m, dict):
                return False
            key = m.get("key", {}) if isinstance(m.get("key"), dict) else {}
            
            # Skip group messages, broadcasts, newsletters
            for raw_jid in [key.get("remoteJid"), m.get("remoteJid"), m.get("chatId")]:
                if raw_jid and ("@g.us" in str(raw_jid) or "@broadcast" in str(raw_jid) or "@newsletter" in str(raw_jid)):
                    return False

            msg_phone = extract_contact_phone_from_message(m)
            if msg_phone:
                if msg_phone == clean_12 or msg_phone == digits:
                    return True
                if len(suffix10) == 10 and (msg_phone.endswith(suffix10) or suffix10 in msg_phone):
                    return True

            for jid_val in [key.get("remoteJidAlt"), key.get("remoteJid"), key.get("participantAlt"), m.get("remoteJid")]:
                if jid_val:
                    j_str = str(jid_val)
                    if j_str in candidate_jids:
                        return True
                    j_base = j_str.split(":")[0] + ("@" + j_str.split("@")[1] if "@" in j_str else "")
                    if j_base in candidate_jids:
                        return True
            return False

        async with httpx.AsyncClient(timeout=25) as client:
            # 1. Discover all candidate instances (passed instance + any open instances in Evolution API)
            candidate_instances = [instance_name] if instance_name else []
            try:
                list_resp = await client.get(self._url("/instance/fetchInstances"), headers=self.headers)
                if list_resp.status_code == 200:
                    inst_data = list_resp.json() if isinstance(list_resp.json(), list) else []
                    for inst in inst_data:
                        name = inst.get("name")
                        if name and name not in candidate_instances:
                            if inst.get("connectionStatus") == "open":
                                candidate_instances.insert(0 if not instance_name else 1, name)
                            else:
                                candidate_instances.append(name)
            except Exception as e:
                logger.debug("Failed to list candidate instances: %s", e)

            for inst in candidate_instances:
                if not inst:
                    continue

                # Strategy 1: "number" field
                for num in candidate_numbers:
                    try:
                        resp = await client.post(
                            self._url(f"/chat/findMessages/{inst}"),
                            headers=self.headers,
                            json={"number": num},
                        )
                        if resp.status_code == 200:
                            messages = self._parse_message_response(resp.json())
                            filtered = [m for m in messages if _is_chat_message(m)]
                            if filtered:
                                logger.info("fetch_messages: got %d messages via number=%s on instance=%s", len(filtered), num, inst)
                                return filtered[:count]
                    except Exception as e:
                        logger.debug("findMessages with number=%s on %s failed: %s", num, inst, e)

                # Strategy 2: "where" filters for remoteJid / remoteJidAlt
                for jid in candidate_jids:
                    for payload in [
                        {"where": {"key": {"remoteJidAlt": jid}}, "limit": count},
                        {"where": {"key": {"remoteJid": jid}}, "limit": count},
                        {"where": {"remoteJid": jid}, "limit": count},
                        {"where": {"key.remoteJid": jid}, "limit": count},
                    ]:
                        try:
                            resp = await client.post(
                                self._url(f"/chat/findMessages/{inst}"),
                                headers=self.headers,
                                json=payload,
                            )
                            if resp.status_code == 200:
                                messages = self._parse_message_response(resp.json())
                                filtered = [m for m in messages if _is_chat_message(m)]
                                if filtered:
                                    logger.info("fetch_messages: got %d messages via where payload on %s (%s)", len(filtered), inst, jid)
                                    return filtered[:count]
                        except Exception as e:
                            logger.debug("findMessages payload %s on %s failed: %s", payload, inst, e)

                # Strategy 3: Batch fetch and client-side filter
                try:
                    for fallback_payload in [{"limit": 100}, {"limit": 50}, {}]:
                        resp = await client.post(
                            self._url(f"/chat/findMessages/{inst}"),
                            headers=self.headers,
                            json=fallback_payload,
                        )
                        if resp.status_code == 200:
                            msgs = self._parse_message_response(resp.json())
                            filtered = [m for m in msgs if _is_chat_message(m)]
                            if filtered:
                                logger.info("fetch_messages: got %d messages via batch fallback on instance %s", len(filtered), inst)
                                return filtered[:count]
                except Exception as e:
                    logger.debug("findMessages batch fallback on %s failed: %s", inst, e)

        logger.info("fetch_messages: no messages found on Evolution API for %s", digits)
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
        content = raw.get("body") or raw.get("content") or raw.get("text") or raw.get("message") or ""
        if isinstance(content, dict):
            message_obj = content
        else:
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
    elif "text" in message_obj and message_obj["text"]:
        content = str(message_obj["text"])
    elif "body" in message_obj and message_obj["body"]:
        content = str(message_obj["body"])
    elif "content" in message_obj and message_obj["content"]:
        content = str(message_obj["content"])
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
        content = str(raw.get("body") or raw.get("content") or raw.get("text") or raw.get("message") or "")

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
            if existing.lead_id is None and lead_id:
                existing.lead_id = lead_id
                existing.user_id = user_id
                existing.instance_name = instance_name
            if not existing.content and content:
                existing.content = content
            return existing, False

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
    if not lead and rep_id is not None:
        lead = await match_lead_by_phone(db, lead_phone)
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
