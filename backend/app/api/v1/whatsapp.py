"""
WhatsApp API Routes — webhook receiver, chat management, and instance control.

Mounted at /api/v1 by main.py, so routes resolve to:
    POST   /api/v1/whatsapp/webhook                       (Evolution API webhook)
    GET    /api/v1/whatsapp/chats                         (List chats for current rep)
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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, func, desc, case
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.base import Lead, User
from app.models.whatsapp_message import WhatsAppMessage, MessageDirection
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
    match_lead_by_phone,
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

    # We only care about new messages
    if event != "messages.upsert":
        return {"status": "ignored", "event": event}

    data = payload.get("data", {})

    # Evolution API v2 wraps messages in a list or directly
    messages = data if isinstance(data, list) else [data]

    for msg_data in messages:
        key = msg_data.get("key", {}) if isinstance(msg_data.get("key"), dict) else {}

        is_from_me = bool(key.get("fromMe", False))

        remote_jid = str(key.get("remoteJid") or msg_data.get("remoteJid") or "")
        # Only process individual chats (not groups)
        if not remote_jid or "@g.us" in remote_jid:
            continue

        # Extract phone from JID: "919876543210@s.whatsapp.net" → "919876543210"
        contact_phone = remote_jid.split("@")[0].split(":")[0]

        # Determine sender and receiver
        if is_from_me:
            sender_phone = instance_name or ""
            receiver_phone = contact_phone
        else:
            sender_phone = contact_phone
            receiver_phone = instance_name or ""

        # Extract message content and media
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
            logger.exception("Failed to process WhatsApp message: %s", exc)

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
    from sqlalchemy import or_

    # Subquery: latest message per lead
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
    for row in rows:
        # Count unread
        unread_result = await db.execute(
            select(func.count(WhatsAppMessage.id)).where(
                WhatsAppMessage.lead_id == row.lead_id,
                WhatsAppMessage.direction == MessageDirection.inbound,
                WhatsAppMessage.status != "read",
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
    """Get the full WhatsApp message history for a specific lead.

    Returns messages ordered by timestamp ascending (oldest first).
    """
    # Verify lead exists and user has access
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
    for msg in messages:
        if msg.direction == MessageDirection.inbound and getattr(msg.status, "value", str(msg.status)) != "read":
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
    """Send a WhatsApp message to a lead from the CRM.

    Requires the current user to have a connected WhatsApp instance.
    """
    # Verify lead
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if not lead.phone_number:
        raise HTTPException(status_code=400, detail="Lead has no phone number")

    if current_user.is_sales_rep and lead.assigned_rep_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Determine the instance name for this user
    # Convention: instance_name = "rep_{user_id}"
    instance_name = f"rep_{current_user.id}"

    # Auto-handle 10-digit numbers by prepending 91
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
# Instance Management (QR Code, Connection)
# ═══════════════════════════════════════════════════════════════════════

@router.post("/instances/create", response_model=InstanceStatusResponse)
async def create_instance(
    body: InstanceCreateRequest,
    current_user: User = Depends(get_current_user),
):
    """Create a new Evolution API instance for WhatsApp connection.

    After creation, the frontend should poll the QR endpoint to display
    the QR code for the sales rep to scan with their phone.
    """
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
    """Fetch the QR code for an instance that's waiting for scan."""
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
        # If it's a 404 or fails, it likely means the instance doesn't exist yet.
        # We return not_created so the frontend knows to call create_instance.
        logger.warning("Failed to check instance status for %s (likely not created): %s", instance_name, exc)
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
    """Log out (disconnect) the current user's WhatsApp instance.
    
    This severs the connection to WhatsApp. The user will need to scan
    a new QR code to reconnect.
    """
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
        # Sales reps only see their own instance
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
# Start Chat — leads without any WhatsApp messages
# ═══════════════════════════════════════════════════════════════════════

@router.get("/leads/without-chats")
async def leads_without_chats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return CRM leads that have NO WhatsApp messages yet.

    Used by the 'Start Chat' modal to show a lead picker. Only returns
    leads with a phone number so a WhatsApp session can be initiated.
    Sales reps see only their assigned leads; managers see all.
    """
    # Sub-select: lead IDs that already have at least one message
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
# Sync History — bulk-import past messages from Evolution API
# ═══════════════════════════════════════════════════════════════════════

@router.post("/chats/{lead_id}/sync-history")
async def sync_chat_history(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch past WhatsApp messages from Evolution API and import into the CRM.

    Reaches out to the Evolution API's findMessages endpoint, filters for
    this lead's phone number, deduplicates, and saves all new messages.
    Returns a count of newly imported messages.
    """
    from sqlalchemy import delete, or_

    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if not lead.phone_number:
        raise HTTPException(status_code=400, detail="Lead has no phone number — add one first")

    if current_user.is_sales_rep and lead.assigned_rep_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    instance_name = f"rep_{current_user.id}"

    # Build normalized phone numbers
    clean_phone = _normalise_phone_for_wa(lead.phone_number)
    digits = _extract_digits(lead.phone_number)
    suffix10 = digits[-10:] if len(digits) >= 10 else digits

    imported = 0

    # Step A: Clean up any corrupted messages erroneously assigned to this lead from other contacts
    if len(suffix10) == 10:
        corrupted_res = await db.execute(
            select(WhatsAppMessage).where(
                WhatsAppMessage.lead_id == lead_id,
                ~WhatsAppMessage.sender_phone.like(f"%{suffix10}%"),
                ~WhatsAppMessage.receiver_phone.like(f"%{suffix10}%"),
                WhatsAppMessage.content != "[Chat Initialised - No previous history found]",
            )
        )
        for bad_msg in corrupted_res.scalars().all():
            real_phone = bad_msg.sender_phone if bad_msg.direction == MessageDirection.inbound else bad_msg.receiver_phone
            real_lead = await match_lead_by_phone(db, real_phone)
            bad_msg.lead_id = real_lead.id if real_lead else None

    # Step B: Link only unlinked orphan messages (where lead_id IS NULL)
    if len(suffix10) == 10:
        orphan_res = await db.execute(
            select(WhatsAppMessage).where(
                WhatsAppMessage.lead_id.is_(None),
                or_(
                    WhatsAppMessage.sender_phone.like(f"%{suffix10}%"),
                    WhatsAppMessage.receiver_phone.like(f"%{suffix10}%"),
                ),
            )
        )
        for orphan in orphan_res.scalars().all():
            orphan.lead_id = lead_id
            orphan.user_id = lead.assigned_rep_id or current_user.id
            orphan.instance_name = instance_name
            imported += 1

    # Step C: Fetch historical messages from Evolution API (up to 50)
    raw_messages = []
    try:
        raw_messages = await evo_client.fetch_messages(instance_name, clean_phone, count=50)
    except Exception as exc:
        logger.warning("fetch_messages failed for %s: %s", instance_name, exc)
        raw_messages = []

    for raw in raw_messages:
        if not isinstance(raw, dict):
            continue

        key = raw.get("key", {}) if isinstance(raw.get("key"), dict) else {}
        wa_msg_id = key.get("id") or raw.get("id") or raw.get("whatsapp_msg_id")
        from_me = bool(key.get("fromMe") if "fromMe" in key else raw.get("fromMe", False))

        # Skip group messages
        jid = key.get("remoteJid") or raw.get("remoteJid", "")
        if "@g.us" in str(jid):
            continue

        # Extract content & media type
        message_obj = raw.get("message")
        content, media_type = extract_content_and_media(message_obj, raw)

        # Parse timestamp
        ts = extract_timestamp(raw)

        # Dedup by whatsapp_msg_id
        if wa_msg_id:
            existing_res = await db.execute(
                select(WhatsAppMessage).where(WhatsAppMessage.whatsapp_msg_id == str(wa_msg_id))
            )
            existing = existing_res.scalar_one_or_none()
            if existing:
                if existing.lead_id is None:
                    existing.lead_id = lead_id
                    existing.user_id = lead.assigned_rep_id or current_user.id
                    existing.instance_name = instance_name
                    imported += 1
                elif existing.lead_id == lead_id:
                    if not existing.content and content:
                        existing.content = content
                continue

        direction = MessageDirection.outbound if from_me else MessageDirection.inbound
        sender = instance_name if from_me else clean_phone
        receiver = clean_phone if from_me else instance_name

        synthetic_id = str(wa_msg_id) if wa_msg_id else f"evo_{lead_id}_{int(ts.timestamp())}_{1 if from_me else 0}"

        msg = WhatsAppMessage(
            lead_id=lead_id,
            user_id=lead.assigned_rep_id or current_user.id,
            whatsapp_msg_id=synthetic_id,
            instance_name=instance_name,
            sender_phone=sender,
            receiver_phone=receiver,
            direction=direction,
            content=content if content else None,
            media_type=media_type,
            status=MessageStatus.delivered,
            timestamp=ts,
        )
        db.add(msg)
        imported += 1

    # Clean up placeholder message if we have real messages
    total_real_res = await db.execute(
        select(func.count(WhatsAppMessage.id)).where(
            WhatsAppMessage.lead_id == lead_id,
            WhatsAppMessage.content != "[Chat Initialised - No previous history found]",
        )
    )
    real_count = total_real_res.scalar() or 0

    if real_count > 0 or imported > 0:
        await db.execute(
            delete(WhatsAppMessage).where(
                WhatsAppMessage.lead_id == lead_id,
                WhatsAppMessage.content == "[Chat Initialised - No previous history found]",
            )
        )
        await db.commit()
    else:
        # Check if any message exists for this lead
        existing_chat = await db.execute(
            select(WhatsAppMessage).where(WhatsAppMessage.lead_id == lead_id)
        )
        if not existing_chat.scalars().first():
            sys_msg = WhatsAppMessage(
                lead_id=lead_id,
                user_id=lead.assigned_rep_id or current_user.id,
                whatsapp_msg_id=f"sys_init_{lead_id}_{int(datetime.now().timestamp())}",
                instance_name=instance_name,
                sender_phone=instance_name,
                receiver_phone=clean_phone,
                direction=MessageDirection.outbound,
                content="[Chat Initialised - No previous history found]",
                status=MessageStatus.delivered,
                timestamp=datetime.now(timezone.utc),
            )
            db.add(sys_msg)
            await db.commit()

    total_all_res = await db.execute(
        select(func.count(WhatsAppMessage.id)).where(
            WhatsAppMessage.lead_id == lead_id,
            WhatsAppMessage.content != "[Chat Initialised - No previous history found]",
        )
    )
    final_total = total_all_res.scalar() or 0

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
    """Delete all WhatsApp messages associated with a lead.

    This hides the chat from the inbox. The actual messages on the WhatsApp
    app itself are not deleted, only the CRM records.
    """
    from sqlalchemy import delete

    # Check permission
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if current_user.is_sales_rep and lead.assigned_rep_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Delete messages
    await db.execute(
        delete(WhatsAppMessage).where(WhatsAppMessage.lead_id == lead_id)
    )
    await db.commit()

    return {"status": "success", "message": "Chat deleted"}
