"""
WhatsApp API Routes — webhook receiver, chat management, and instance control.

Mounted at /api/v1 by main.py, so routes resolve to:
    POST   /api/v1/whatsapp/webhook                       (Evolution API webhook)
    GET    /api/v1/whatsapp/chats                         (List chats for current rep)
    GET    /api/v1/whatsapp/chats/{lead_id}               (Message history for a lead)
    POST   /api/v1/whatsapp/chats/{lead_id}/send          (Send message to a lead)
    DELETE /api/v1/whatsapp/chats/{lead_id}               (Delete a chat conversation)
    POST   /api/v1/whatsapp/chats/{lead_id}/sync-history  (Additive sync from Evolution API)
    GET    /api/v1/whatsapp/leads/without-chats           (Leads with no WhatsApp messages yet)
    POST   /api/v1/whatsapp/instances/create              (Create a WhatsApp session)
    GET    /api/v1/whatsapp/instances/qr/{name}           (Fetch QR code for scanning)
    GET    /api/v1/whatsapp/instances/status/{name}       (Check connection status)
    POST   /api/v1/whatsapp/instances/logout              (Disconnect from WhatsApp)
    GET    /api/v1/whatsapp/instances                     (List all instances)
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.base import Lead, User
from app.models.whatsapp_message import WhatsAppMessage, MessageDirection, MessageStatus
from app.schemas.whatsapp import (
    WhatsAppMessageRead,
    WhatsAppSendMessage,
    WhatsAppChatSummary,
    InstanceCreateRequest,
    InstanceStatusResponse,
)
from app.api.dependencies import get_current_user
from app.services.whatsapp import (
    evo_client,
    process_incoming_message,
    save_outbound_message,
    upsert_message,
    match_lead_by_phone,
    _normalise_phone_for_wa,
    extract_content_and_media,
    extract_timestamp,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])


# ═══════════════════════════════════════════════════════════════════════
# Webhook — receives messages from Evolution API
# ═══════════════════════════════════════════════════════════════════════

@router.post("/webhook", include_in_schema=False)
async def whatsapp_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive incoming message events from Evolution API.

    Evolution API sends POST payloads for various events. We only process
    'messages.upsert' events containing actual message content.
    """
    try:
        payload = await request.json()
    except Exception:
        logger.warning("Invalid JSON in WhatsApp webhook")
        return {"status": "ignored"}

    event = payload.get("event")
    instance_name = payload.get("instance")

    if event != "messages.upsert":
        return {"status": "ignored", "event": event}

    data = payload.get("data", {})
    messages = data if isinstance(data, list) else [data]

    for msg_data in messages:
        key = msg_data.get("key", {})
        is_from_me = key.get("fromMe", False)
        remote_jid = key.get("remoteJid", "")

        # Skip groups
        if not remote_jid or "@g.us" in remote_jid:
            continue

        contact_phone = remote_jid.split("@")[0]

        if is_from_me:
            sender_phone = instance_name or ""
            receiver_phone = contact_phone
        else:
            sender_phone = contact_phone
            receiver_phone = instance_name or ""

        message_obj = msg_data.get("message", {})
        content = (
            message_obj.get("conversation")
            or (message_obj.get("extendedTextMessage") or {}).get("text")
            or ""
        )

        media_type = None
        media_url = None
        if "imageMessage" in message_obj:
            media_type = "image"
            content = content or (message_obj.get("imageMessage") or {}).get("caption", "[Image]")
        elif "videoMessage" in message_obj:
            media_type = "video"
            content = content or "[Video]"
        elif "audioMessage" in message_obj:
            media_type = "audio"
            content = content or "[Voice Note]"
        elif "documentMessage" in message_obj:
            media_type = "document"
            content = content or (message_obj.get("documentMessage") or {}).get("fileName", "[Document]")

        whatsapp_msg_id = key.get("id")
        msg_timestamp = msg_data.get("messageTimestamp")
        ts = None
        if msg_timestamp:
            try:
                ts = datetime.fromtimestamp(int(msg_timestamp), tz=timezone.utc)
            except (ValueError, TypeError):
                ts = None

        try:
            await process_incoming_message(
                db,
                instance_name=instance_name or "",
                sender_phone=sender_phone,
                receiver_phone=receiver_phone,
                content=content if content else None,
                whatsapp_msg_id=whatsapp_msg_id,
                media_type=media_type,
                media_url=media_url,
                timestamp=ts,
                is_from_me=is_from_me,
            )
        except Exception as exc:
            logger.exception("Failed to process WhatsApp webhook message: %s", exc)

    return {"status": "processed"}


# ═══════════════════════════════════════════════════════════════════════
# Chat List & Messages
# ═══════════════════════════════════════════════════════════════════════

@router.get("/chats", response_model=list[WhatsAppChatSummary])
async def list_chats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all WhatsApp conversations for the current user.

    Returns a summary per lead: last message, timestamp, and unread count.
    Managers/admins see all chats; sales reps see only their assigned leads.
    """
    instance_name = f"rep_{current_user.id}"

    latest_msg_sq = (
        select(
            WhatsAppMessage.lead_id,
            func.max(WhatsAppMessage.timestamp).label("last_ts"),
        )
        .where(
            WhatsAppMessage.lead_id.isnot(None),
            WhatsAppMessage.instance_name == instance_name,
        )
        .group_by(WhatsAppMessage.lead_id)
        .subquery()
    )

    query = (
        select(
            Lead.id.label("lead_id"),
            Lead.name.label("lead_name"),
            Lead.phone_number.label("lead_phone"),
            Lead.status.label("lead_status"),
            WhatsAppMessage.content.label("last_message"),
            WhatsAppMessage.timestamp.label("last_message_time"),
            WhatsAppMessage.direction.label("direction"),
        )
        .join(latest_msg_sq, Lead.id == latest_msg_sq.c.lead_id)
        .join(
            WhatsAppMessage,
            (WhatsAppMessage.lead_id == Lead.id)
            & (WhatsAppMessage.timestamp == latest_msg_sq.c.last_ts),
        )
    )

    if current_user.is_sales_rep:
        query = query.where(Lead.assigned_rep_id == current_user.id)

    query = query.order_by(desc(latest_msg_sq.c.last_ts))
    result = await db.execute(query)
    rows = result.all()

    chats = []
    for row in rows:
        unread_result = await db.execute(
            select(func.count(WhatsAppMessage.id)).where(
                WhatsAppMessage.lead_id == row.lead_id,
                WhatsAppMessage.direction == MessageDirection.inbound,
                WhatsAppMessage.status != "read",
                WhatsAppMessage.instance_name == instance_name,
            )
        )
        unread_count = unread_result.scalar() or 0

        chats.append(WhatsAppChatSummary(
            lead_id=row.lead_id,
            lead_name=row.lead_name,
            lead_phone=row.lead_phone or "",
            lead_status=row.lead_status.value if row.lead_status else None,
            last_message=(row.last_message or "")[:100],
            last_message_time=row.last_message_time,
            unread_count=unread_count,
            direction=row.direction.value if row.direction else None,
        ))

    return chats


@router.get("/chats/{lead_id}", response_model=list[WhatsAppMessageRead])
async def get_chat_messages(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the full WhatsApp message history for a specific lead (oldest first)."""
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if current_user.is_sales_rep and lead.assigned_rep_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    instance_name = f"rep_{current_user.id}"

    result = await db.execute(
        select(WhatsAppMessage)
        .where(
            WhatsAppMessage.lead_id == lead_id,
            WhatsAppMessage.instance_name == instance_name,
        )
        .order_by(WhatsAppMessage.timestamp.asc())
    )
    messages = result.scalars().all()

    # Mark inbound messages as read
    for msg in messages:
        if msg.direction == MessageDirection.inbound and msg.status.value != "read":
            msg.status = "read"
    await db.commit()

    return messages


@router.post("/chats/{lead_id}/send", response_model=WhatsAppMessageRead)
async def send_message(
    lead_id: int,
    body: WhatsAppSendMessage,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a WhatsApp message to a lead from the CRM."""
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if not lead.phone_number:
        raise HTTPException(status_code=400, detail="Lead has no phone number")

    if current_user.is_sales_rep and lead.assigned_rep_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    instance_name = f"rep_{current_user.id}"
    clean_phone = _normalise_phone_for_wa(lead.phone_number)

    try:
        evo_resp = await evo_client.send_text_message(
            instance_name=instance_name,
            phone=clean_phone,
            text=body.content,
        )
    except Exception as exc:
        logger.exception("Evolution API send failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Failed to send WhatsApp message. Check your WhatsApp connection.",
        )

    wa_msg_id = None
    if isinstance(evo_resp, dict):
        key = evo_resp.get("key", {})
        wa_msg_id = key.get("id") if isinstance(key, dict) else None

    msg = await save_outbound_message(
        db,
        lead_id=lead_id,
        user_id=current_user.id,
        instance_name=instance_name,
        sender_phone=current_user.phone_number or instance_name,
        receiver_phone=lead.phone_number,
        content=body.content,
        whatsapp_msg_id=wa_msg_id,
    )

    return msg


# ═══════════════════════════════════════════════════════════════════════
# Sync History — additive import from Evolution API (NO WIPE)
# ═══════════════════════════════════════════════════════════════════════

@router.post("/chats/{lead_id}/sync-history")
async def sync_chat_history(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sync the complete conversation history for a lead from Evolution API.

    Behaviour:
    - Fetches ALL messages for this contact (old + new, inbound + outbound).
    - For each message: if already in DB → skip; if missing → insert.
    - NO messages are ever deleted. Always safe, always additive.
    - If Evolution API returns 0 messages and the lead has no chat yet,
      inserts a placeholder so the lead appears in the sidebar.

    Returns: {"imported": N, "already_synced": M, "lead_id": lead_id}
    """
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if not lead.phone_number:
        raise HTTPException(status_code=400, detail="Lead has no phone number — add one first")

    if current_user.is_sales_rep and lead.assigned_rep_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    instance_name = f"rep_{current_user.id}"
    clean_phone = _normalise_phone_for_wa(lead.phone_number)
    user_id = lead.assigned_rep_id or current_user.id

    # ── Fetch ALL messages from Evolution API ──────────────────────────
    fetch_error = None
    raw_messages = []
    try:
        raw_messages = await evo_client.fetch_messages_for_contact(
            instance_name, lead.phone_number, limit=1000
        )
    except Exception as exc:
        fetch_error = str(exc)
        logger.exception(
            "sync_chat_history: Evolution API fetch failed for lead %d: %s", lead_id, exc
        )

    logger.info(
        "sync_chat_history: fetched %d raw for lead %d (phone=%s, fetch_error=%s)",
        len(raw_messages), lead_id, lead.phone_number, fetch_error,
    )

    # ── If fetch failed entirely, don't destroy existing messages ──────
    if fetch_error and not raw_messages:
        existing_count_result = await db.execute(
            select(func.count(WhatsAppMessage.id)).where(
                WhatsAppMessage.lead_id == lead_id,
                WhatsAppMessage.instance_name == instance_name,
            )
        )
        existing_count = existing_count_result.scalar() or 0
        if existing_count == 0:
            raise HTTPException(
                status_code=502,
                detail="Could not fetch history from WhatsApp. Make sure your WhatsApp is connected.",
            )
        return {"imported": 0, "already_synced": existing_count, "lead_id": lead_id}

    # ── Evolution API returned 0 messages ─────────────────────────────
    # Insert a placeholder so the lead appears in the sidebar. This is
    # critical for the "Start Fresh" flow — without it the lead never
    # shows up in the chat list and the user can't open it to send a msg.
    if not raw_messages:
        existing_check = await db.execute(
            select(WhatsAppMessage.id).where(
                WhatsAppMessage.lead_id == lead_id,
                WhatsAppMessage.instance_name == instance_name,
            ).limit(1)
        )
        if not existing_check.scalar():
            placeholder_id = f"placeholder_{lead_id}_{instance_name}"
            dup_check = await db.execute(
                select(WhatsAppMessage).where(
                    WhatsAppMessage.whatsapp_msg_id == placeholder_id
                )
            )
            if not dup_check.scalar_one_or_none():
                db.add(WhatsAppMessage(
                    lead_id=lead_id,
                    user_id=user_id,
                    whatsapp_msg_id=placeholder_id,
                    instance_name=instance_name,
                    sender_phone=instance_name,
                    receiver_phone=clean_phone,
                    direction=MessageDirection.outbound,
                    content="💬 Chat started — send your first message!",
                    status=MessageStatus.delivered,
                    timestamp=datetime.now(timezone.utc),
                ))
                await db.commit()
                logger.info("sync_chat_history: inserted placeholder for lead %d", lead_id)
        return {
            "imported": 0,
            "already_synced": 0,
            "lead_id": lead_id,
            "message": "No conversation history found in WhatsApp for this number.",
        }

    # ── Upsert each message — skip existing, insert new ───────────────
    imported = 0
    already_synced = 0
    errors = 0

    for raw in raw_messages:
        try:
            key_d = raw.get("key", {}) if isinstance(raw.get("key"), dict) else {}

            # Skip group messages
            jid = str(key_d.get("remoteJid") or raw.get("remoteJid") or "")
            if "@g.us" in jid or "@broadcast" in jid:
                continue

            wa_msg_id = key_d.get("id") or raw.get("id")
            from_me = bool(
                key_d.get("fromMe") if "fromMe" in key_d else raw.get("fromMe", False)
            )

            content, media_type = extract_content_and_media(raw.get("message"), raw)
            ts = extract_timestamp(raw)

            if not wa_msg_id:
                wa_msg_id = f"sync_{lead_id}_{int(ts.timestamp())}_{1 if from_me else 0}"

            direction = MessageDirection.outbound if from_me else MessageDirection.inbound
            sender = instance_name if from_me else clean_phone
            receiver = clean_phone if from_me else instance_name

            _msg, is_new = await upsert_message(
                db,
                lead_id=lead_id,
                user_id=user_id,
                instance_name=instance_name,
                sender_phone=sender,
                receiver_phone=receiver,
                direction=direction,
                content=content if content else None,
                whatsapp_msg_id=str(wa_msg_id),
                media_type=media_type,
                status=MessageStatus.delivered,
                timestamp=ts,
            )

            if is_new:
                imported += 1
            else:
                already_synced += 1

        except Exception as exc:
            errors += 1
            logger.warning(
                "sync_chat_history: error upserting message for lead %d: %s", lead_id, exc
            )
            continue

    await db.commit()

    logger.info(
        "sync_chat_history: lead %d — imported=%d, already_synced=%d, errors=%d",
        lead_id, imported, already_synced, errors,
    )
    return {
        "imported": imported,
        "already_synced": already_synced,
        "lead_id": lead_id,
    }


# ═══════════════════════════════════════════════════════════════════════
# Delete Chat
# ═══════════════════════════════════════════════════════════════════════

@router.delete("/chats/{lead_id}")
async def delete_chat(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete all WhatsApp messages for a lead from the CRM (hides the chat).

    The actual messages on WhatsApp are not deleted — only the CRM records.
    """
    from sqlalchemy import delete

    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if current_user.is_sales_rep and lead.assigned_rep_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    await db.execute(
        delete(WhatsAppMessage).where(WhatsAppMessage.lead_id == lead_id)
    )
    await db.commit()

    return {"status": "success", "message": "Chat deleted"}


# ═══════════════════════════════════════════════════════════════════════
# Start Chat — leads without any WhatsApp messages
# ═══════════════════════════════════════════════════════════════════════

@router.get("/leads/without-chats")
async def leads_without_chats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return CRM leads that have NO WhatsApp messages yet (for the Start Chat modal)."""
    existing_sq = (
        select(WhatsAppMessage.lead_id)
        .where(WhatsAppMessage.lead_id.isnot(None))
        .distinct()
        .subquery()
    )

    query = (
        select(Lead)
        .where(
            Lead.phone_number.isnot(None),
            Lead.phone_number != "",
            Lead.id.not_in(select(existing_sq)),
        )
        .order_by(Lead.name.asc())
    )

    if current_user.is_sales_rep:
        query = query.where(Lead.assigned_rep_id == current_user.id)

    result = await db.execute(query)
    leads = result.scalars().all()

    return [
        {
            "id": lead.id,
            "name": lead.name,
            "phone_number": lead.phone_number,
            "status": lead.status.value if lead.status else None,
        }
        for lead in leads
    ]


# ═══════════════════════════════════════════════════════════════════════
# Instance Management (QR Code, Connection)
# ═══════════════════════════════════════════════════════════════════════

@router.post("/instances/create", response_model=InstanceStatusResponse)
async def create_instance(
    body: InstanceCreateRequest,
    current_user: User = Depends(get_current_user),
):
    """Create a new Evolution API instance for WhatsApp connection."""
    try:
        result = await evo_client.create_instance(body.instance_name)
    except Exception as exc:
        logger.exception("Failed to create Evolution instance: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to create WhatsApp instance")

    qr = None
    if isinstance(result, dict):
        qr = (
            result.get("qrcode", {}).get("base64")
            if isinstance(result.get("qrcode"), dict)
            else result.get("qrcode")
        )

    return InstanceStatusResponse(
        instance_name=body.instance_name,
        status="connecting",
        qr_code=qr,
    )


@router.get("/instances/qr/{instance_name}", response_model=InstanceStatusResponse)
async def get_instance_qr(
    instance_name: str,
    current_user: User = Depends(get_current_user),
):
    """Fetch the QR code for an instance waiting for scan."""
    try:
        result = await evo_client.get_qr_code(instance_name)
    except Exception as exc:
        logger.exception("Failed to fetch QR code: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to fetch QR code")

    qr = None
    if isinstance(result, dict):
        qr = result.get("base64") or result.get("code")

    return InstanceStatusResponse(
        instance_name=instance_name,
        status="connecting",
        qr_code=qr,
    )


@router.get("/instances/status/{instance_name}", response_model=InstanceStatusResponse)
async def get_instance_status(
    instance_name: str,
    current_user: User = Depends(get_current_user),
):
    """Check the connection status of a WhatsApp instance."""
    try:
        result = await evo_client.get_instance_status(instance_name)
    except Exception as exc:
        logger.warning(
            "Failed to check instance status for %s (likely not created): %s",
            instance_name, exc,
        )
        return InstanceStatusResponse(
            instance_name=instance_name,
            status="not_created",
            qr_code=None,
        )

    conn_state = "close"
    if isinstance(result, dict):
        instance_data = result.get("instance", result)
        conn_state = instance_data.get("state", "close")

    return InstanceStatusResponse(
        instance_name=instance_name,
        status=conn_state,
        qr_code=None,
    )


@router.post("/instances/logout")
async def logout_instance(
    current_user: User = Depends(get_current_user),
):
    """Log out (disconnect) the current user's WhatsApp instance."""
    instance_name = f"rep_{current_user.id}"
    try:
        await evo_client.logout_instance(instance_name)
        return {"status": "success", "message": "WhatsApp disconnected successfully"}
    except Exception as exc:
        logger.error("Failed to logout instance %s: %s", instance_name, exc)
        raise HTTPException(status_code=502, detail="Failed to disconnect from WhatsApp")


@router.get("/instances")
async def list_instances(
    current_user: User = Depends(get_current_user),
):
    """List all registered Evolution API instances (admin/manager only)."""
    if current_user.is_sales_rep:
        instance_name = f"rep_{current_user.id}"
        try:
            result = await evo_client.get_instance_status(instance_name)
            state = "close"
            if isinstance(result, dict):
                instance_data = result.get("instance", result)
                state = instance_data.get("state", "close")
            return [{"instance_name": instance_name, "status": state}]
        except Exception:
            return [{"instance_name": instance_name, "status": "not_created"}]

    try:
        instances = await evo_client.list_instances()
        return instances
    except Exception as exc:
        logger.exception("Failed to list instances: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to list instances")


# ═══════════════════════════════════════════════════════════════════════
# Debug Endpoints (Admin / Manager only)
# ═══════════════════════════════════════════════════════════════════════

@router.get("/debug/contacts/{instance_name}")
async def debug_contacts(
    instance_name: str,
    current_user: User = Depends(get_current_user),
):
    """Debug: Fetch raw contacts from Evolution API."""
    if (
        not current_user.is_admin
        and not current_user.is_manager
        and f"rep_{current_user.id}" != instance_name
    ):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        contacts = await evo_client.find_contacts(instance_name)
        return {"count": len(contacts), "contacts": contacts}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/debug/chats/{instance_name}")
async def debug_chats(
    instance_name: str,
    current_user: User = Depends(get_current_user),
):
    """Debug: Fetch raw chats from Evolution API."""
    if (
        not current_user.is_admin
        and not current_user.is_manager
        and f"rep_{current_user.id}" != instance_name
    ):
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        chats = await evo_client.find_chats(instance_name)
        return {"count": len(chats), "chats": chats}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
