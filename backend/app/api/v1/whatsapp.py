"""
WhatsApp API Routes — webhook receiver, chat management, and instance control.

Mounted at /api/v1 by main.py, so routes resolve to:
    POST   /api/v1/whatsapp/webhook                       (Evolution API webhook)
    GET    /api/v1/whatsapp/chats                         (List chats for current user)
    GET    /api/v1/whatsapp/chats/{lead_id}               (Message history for a lead)
    POST   /api/v1/whatsapp/chats/{lead_id}/send          (Send message to a lead)
    DELETE /api/v1/whatsapp/chats/{lead_id}               (Delete a chat conversation)
    POST   /api/v1/whatsapp/chats/{lead_id}/sync-history  (Import historical messages from Evo API)
    GET    /api/v1/whatsapp/leads/without-chats           (Leads with no WhatsApp messages yet)
    POST   /api/v1/whatsapp/instances/create              (Create a WhatsApp session)
    GET    /api/v1/whatsapp/instances/qr/{name}           (Fetch QR code for scanning)
    GET    /api/v1/whatsapp/instances/status/{name}       (Check connection status)
    POST   /api/v1/whatsapp/instances/logout              (Disconnect from WhatsApp)
    GET    /api/v1/whatsapp/instances                     (List all instances)
"""

import logging
from datetime import datetime, timezone
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, func, desc, or_, delete
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
    extract_contact_phone_from_message,
    _normalise_phone_for_wa,
    _extract_digits,
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
    """Receive incoming message events from Evolution API."""
    try:
        payload = await request.json()
    except Exception:
        logger.warning("Invalid JSON in WhatsApp webhook")
        return {"status": "ignored"}

    event = payload.get("event")
    instance_name = payload.get("instance")

    # We care about messages upsert, set (history load), and update events
    if event not in ("messages.upsert", "messages.set", "messages.update"):
        return {"status": "ignored", "event": event}

    data = payload.get("data", {})

    if isinstance(data, dict) and "messages" in data and isinstance(data["messages"], list):
        messages = data["messages"]
    elif isinstance(data, list):
        messages = data
    else:
        messages = [data]

    for msg_data in messages:
        if not isinstance(msg_data, dict):
            continue

        key = msg_data.get("key", {}) if isinstance(msg_data.get("key"), dict) else {}
        is_from_me = bool(key.get("fromMe", False))

        remote_jid = str(key.get("remoteJid") or msg_data.get("remoteJid") or "")
        # Only process individual chats (not groups, broadcasts, newsletters)
        if not remote_jid or any(x in remote_jid for x in ("@g.us", "@broadcast", "@newsletter")):
            continue

        # Extract real contact phone
        contact_phone = extract_contact_phone_from_message(msg_data)
        if not contact_phone:
            contact_phone = remote_jid.split("@")[0].split(":")[0]
            if not contact_phone:
                continue

        # Determine sender and receiver
        if is_from_me:
            sender_phone = instance_name or ""
            receiver_phone = contact_phone
        else:
            sender_phone = contact_phone
            receiver_phone = instance_name or ""

        message_obj = msg_data.get("message")
        content, media_type = extract_content_and_media(message_obj, msg_data)

        whatsapp_msg_id = key.get("id") or msg_data.get("id")
        ts = extract_timestamp(msg_data)

        try:
            await process_incoming_message(
                db,
                instance_name=instance_name or "",
                sender_phone=sender_phone,
                receiver_phone=receiver_phone,
                content=content if content else None,
                whatsapp_msg_id=str(whatsapp_msg_id) if whatsapp_msg_id else None,
                media_type=media_type,
                media_url=None,
                timestamp=ts,
                is_from_me=is_from_me,
            )
        except Exception as exc:
            logger.exception("Failed to process WhatsApp webhook message: %s", exc)

    return {"status": "processed"}


# ═══════════════════════════════════════════════════════════════════════
# Chat List & Messages
# ═══════════════════════════════════════════════════════════════════════

@router.get("/chats", response_model=List[WhatsAppChatSummary])
async def list_chats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all WhatsApp conversations for the current user.

    Returns a summary per lead: last message, timestamp, and unread count.
    Managers/admins see all chats; sales reps see only their assigned leads.
    """
    # Subquery: latest message timestamp per lead
    latest_msg_sq = (
        select(
            WhatsAppMessage.lead_id,
            func.max(WhatsAppMessage.timestamp).label("last_ts"),
        )
        .where(WhatsAppMessage.lead_id.isnot(None))
        .group_by(WhatsAppMessage.lead_id)
        .subquery()
    )

    # Main query: join latest message with lead details
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

    # RBAC: sales reps only see their own assigned leads
    if current_user.is_sales_rep:
        query = query.where(Lead.assigned_rep_id == current_user.id)

    query = query.order_by(desc(latest_msg_sq.c.last_ts))
    result = await db.execute(query)
    rows = result.all()

    chats = []
    seen_lead_ids = set()
    for row in rows:
        if row.lead_id in seen_lead_ids:
            continue
        seen_lead_ids.add(row.lead_id)

        # Count unread messages
        unread_result = await db.execute(
            select(func.count(WhatsAppMessage.id)).where(
                WhatsAppMessage.lead_id == row.lead_id,
                WhatsAppMessage.direction == MessageDirection.inbound,
                WhatsAppMessage.status != MessageStatus.read,
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


@router.get("/chats/{lead_id}", response_model=List[WhatsAppMessageRead])
async def get_chat_messages(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the full WhatsApp message history for a specific lead ordered chronologically."""
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if current_user.is_sales_rep and lead.assigned_rep_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(WhatsAppMessage)
        .where(WhatsAppMessage.lead_id == lead_id)
        .order_by(WhatsAppMessage.timestamp.asc())
    )
    messages = result.scalars().all()

    # Mark inbound messages as read
    marked_any = False
    for msg in messages:
        if msg.direction == MessageDirection.inbound and msg.status != MessageStatus.read:
            msg.status = MessageStatus.read
            marked_any = True
    if marked_any:
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

    # Send via Evolution API
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

    # Extract message ID from Evolution response
    wa_msg_id = None
    if isinstance(evo_resp, dict):
        key = evo_resp.get("key", {})
        wa_msg_id = key.get("id") if isinstance(key, dict) else None

    # Save to DB + timeline
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
# Sync History — bulk-import past messages from Evolution API
# ═══════════════════════════════════════════════════════════════════════

@router.post("/chats/{lead_id}/sync-history")
async def sync_chat_history(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch past WhatsApp messages from Evolution API and import into the CRM.

    Fetches up to 100 historical messages for this lead's phone number across
    connected instances, reconciles unlinked DB messages, and returns imported counts.
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
    digits = _extract_digits(lead.phone_number)
    suffix10 = digits[-10:] if len(digits) >= 10 else digits
    user_id = lead.assigned_rep_id or current_user.id

    imported = 0

    # Step A: Link any existing unlinked messages in DB matching this contact's phone
    if suffix10:
        unlinked_res = await db.execute(
            select(WhatsAppMessage).where(
                or_(
                    WhatsAppMessage.sender_phone.like(f"%{suffix10}%"),
                    WhatsAppMessage.receiver_phone.like(f"%{suffix10}%"),
                )
            )
        )
        for unlinked in unlinked_res.scalars().all():
            if unlinked.lead_id != lead_id:
                unlinked.lead_id = lead_id
                unlinked.user_id = user_id
                imported += 1

    # Step B: Fetch historical messages from Evolution API
    raw_messages = []
    try:
        raw_messages = await evo_client.fetch_messages(instance_name, clean_phone, count=100)
        logger.info("sync_chat_history: fetched %d raw messages for lead %d", len(raw_messages), lead_id)
    except Exception as exc:
        logger.warning("fetch_messages failed for lead %d (%s): %s", lead_id, instance_name, exc)

    for raw in raw_messages:
        if not isinstance(raw, dict):
            continue

        key = raw.get("key", {}) if isinstance(raw.get("key"), dict) else {}
        wa_msg_id = key.get("id") or raw.get("id") or raw.get("whatsapp_msg_id")
        from_me = bool(key.get("fromMe") if "fromMe" in key else raw.get("fromMe", False))

        # Skip group messages, broadcasts, newsletters
        jid = str(key.get("remoteJid") or raw.get("remoteJid") or raw.get("chatId") or "")
        if any(x in jid for x in ("@g.us", "@broadcast", "@newsletter")):
            continue

        # Extract content & media type
        message_obj = raw.get("message")
        content, media_type = extract_content_and_media(message_obj, raw)

        # Parse timestamp
        ts = extract_timestamp(raw)

        # Unique synthetic ID if WA ID not present
        msg_id = str(wa_msg_id) if wa_msg_id else f"evo_{lead_id}_{int(ts.timestamp())}_{1 if from_me else 0}"

        direction = MessageDirection.outbound if from_me else MessageDirection.inbound
        sender = instance_name if from_me else clean_phone
        receiver = clean_phone if from_me else instance_name

        # Dedup and persist via unified upsert
        _msg, is_new = await upsert_message(
            db,
            lead_id=lead_id,
            user_id=user_id,
            instance_name=instance_name,
            sender_phone=sender,
            receiver_phone=receiver,
            direction=direction,
            content=content if content else None,
            whatsapp_msg_id=msg_id,
            media_type=media_type,
            timestamp=ts,
        )
        if is_new:
            imported += 1

    await db.commit()

    # Count total messages for this lead
    total_res = await db.execute(
        select(func.count(WhatsAppMessage.id)).where(
            WhatsAppMessage.lead_id == lead_id,
        )
    )
    final_total = total_res.scalar() or 0

    logger.info("sync_chat_history: imported %d new messages for lead %d (total: %d)", imported, lead_id, final_total)
    return {"imported": imported, "total": final_total, "lead_id": lead_id}


# ═══════════════════════════════════════════════════════════════════════
# Delete Chat
# ═══════════════════════════════════════════════════════════════════════

@router.delete("/chats/{lead_id}")
async def delete_chat(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete all WhatsApp messages associated with a lead from the CRM DB."""
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
    """Return CRM leads that have NO WhatsApp messages yet."""
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
        qr = result.get("qrcode", {}).get("base64") if isinstance(result.get("qrcode"), dict) else result.get("qrcode")

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
    """Fetch the QR code for an instance that is waiting for scan."""
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
        logger.warning("Failed to check instance status for %s: %s", instance_name, exc)
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
    """List all registered Evolution API instances."""
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
