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

from fastapi import APIRouter, Depends, HTTPException, Request, status
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

        # Extract phone from JID: "919876543210@s.whatsapp.net" → "919876543210"
        contact_phone = remote_jid.split("@")[0]

        if is_from_me:
            sender_phone = instance_name or ""
            receiver_phone = contact_phone
        else:
            sender_phone = contact_phone
            receiver_phone = instance_name or ""

        # Extract content
        message_obj = msg_data.get("message", {})
        content = (
            message_obj.get("conversation")
            or (message_obj.get("extendedTextMessage") or {}).get("text")
            or ""
        )

        # Media detection
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

    # Subquery: latest message timestamp per lead
    latest_msg_sq = (
        select(
            WhatsAppMessage.lead_id,
            func.max(WhatsAppMessage.timestamp).label("last_ts"),
        )
        .where(
            WhatsAppMessage.lead_id.isnot(None),
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

    # Deduplicate in case multiple messages share the exact max timestamp
    seen_leads = set()
    chats = []
    for row in rows:
        if row.lead_id in seen_leads:
            continue
        seen_leads.add(row.lead_id)

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
    Marks inbound messages as read.
    """
    lead = await db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if current_user.is_sales_rep and lead.assigned_rep_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(WhatsAppMessage)
        .where(
            WhatsAppMessage.lead_id == lead_id,
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
    """Send a WhatsApp message to a lead from the CRM.

    Requires the current user to have a connected WhatsApp instance.
    """
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

    # Extract Evolution API's message ID for deduplication
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

    How it works:
    - Fetches ALL messages for this contact (old + new, inbound + outbound)
      from Evolution API's local database.
    - For each message fetched:
        - Already in DB (matched by whatsapp_msg_id) → skipped
        - Not in DB → inserted
    - NO messages are ever deleted. This operation is always safe and additive.

    This means:
    - A first-time sync populates the entire conversation history.
    - Subsequent syncs only insert genuinely new messages.
    - Pressing sync multiple times is idempotent.
    - Old messages missed during webhook downtime are recovered.

    Returns:
        {"imported": N, "already_synced": M, "lead_id": lead_id}
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

    # ── Fetch ALL messages for this contact from Evolution API ─────────
    try:
        raw_messages = await evo_client.fetch_messages_for_contact(
            instance_name, lead.phone_number, limit=1000
        )
    except Exception as exc:
        logger.exception("sync_chat_history: failed to fetch from Evolution API: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Could not fetch history from WhatsApp. Make sure your WhatsApp is connected.",
        )

    logger.info(
        "sync_chat_history: fetched %d raw messages for lead %d (phone=%s)",
        len(raw_messages), lead_id, lead.phone_number,
    )

    if not raw_messages:
        logger.info(
            "sync_chat_history: Evolution API returned 0 messages for lead %d — "
            "no changes made to DB",
            lead_id,
        )
        return {
            "imported": 0,
            "already_synced": 0,
            "lead_id": lead_id,
            "message": "No conversation history found in WhatsApp for this number.",
        }

    # ── Parse and batch deduplicate messages against DB ────────────────
    parsed_items = []
    candidate_ids = []

    for raw in raw_messages:
        key_d = raw.get("key", {}) if isinstance(raw.get("key"), dict) else {}

        # Skip group messages
        jid = str(key_d.get("remoteJid") or raw.get("remoteJid") or "")
        if "@g.us" in jid or "@broadcast" in jid or "@newsletter" in jid:
            continue

        wa_msg_id = key_d.get("id") or raw.get("id")
        from_me = bool(
            key_d.get("fromMe") if "fromMe" in key_d else raw.get("fromMe", False)
        )

        content, media_type = extract_content_and_media(raw.get("message"), raw)
        ts = extract_timestamp(raw)
        if not wa_msg_id:
            wa_msg_id = f"sync_{lead_id}_{int(ts.timestamp())}_{1 if from_me else 0}"

        wa_msg_id_str = str(wa_msg_id)
        candidate_ids.append(wa_msg_id_str)
        parsed_items.append({
            "wa_msg_id": wa_msg_id_str,
            "from_me": from_me,
            "content": content if content else None,
            "media_type": media_type,
            "ts": ts,
        })

    # Batch query existing message IDs in DB in a single SQL roundtrip
    existing_ids = set()
    if candidate_ids:
        # Query in chunks of 500 to avoid query size limits
        chunk_size = 500
        for i in range(0, len(candidate_ids), chunk_size):
            chunk = candidate_ids[i:i + chunk_size]
            res = await db.execute(
                select(WhatsAppMessage.whatsapp_msg_id).where(
                    WhatsAppMessage.whatsapp_msg_id.in_(chunk)
                )
            )
            for row in res.scalars().all():
                if row:
                    existing_ids.add(str(row))

    imported = 0
    already_synced = 0
    seen_in_batch = set()

    for item in parsed_items:
        msg_id = item["wa_msg_id"]
        if msg_id in existing_ids or msg_id in seen_in_batch:
            already_synced += 1
            continue

        seen_in_batch.add(msg_id)
        from_me = item["from_me"]
        direction = MessageDirection.outbound if from_me else MessageDirection.inbound
        sender = instance_name if from_me else clean_phone
        receiver = clean_phone if from_me else instance_name

        msg = WhatsAppMessage(
            lead_id=lead_id,
            user_id=user_id,
            whatsapp_msg_id=msg_id,
            instance_name=instance_name,
            sender_phone=sender,
            receiver_phone=receiver,
            direction=direction,
            content=item["content"],
            media_type=item["media_type"],
            status=MessageStatus.delivered,
            timestamp=item["ts"],
        )
        db.add(msg)
        imported += 1

    await db.commit()

    logger.info(
        "sync_chat_history: lead %d — imported %d new, %d already in DB",
        lead_id, imported, already_synced,
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
    """Delete all WhatsApp messages associated with a lead from the CRM.

    This hides the chat from the inbox. The actual messages on the WhatsApp
    app are not deleted — only the CRM records are removed.
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
    """Return CRM leads that have NO WhatsApp messages yet.

    Used by the 'Start Chat' modal to show a lead picker. Only returns leads
    with a phone number so a WhatsApp session can be initiated.
    Sales reps see only their assigned leads; managers see all.
    """
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
    """Log out (disconnect) the current user's WhatsApp instance.

    This severs the connection to WhatsApp. The user will need to scan
    a new QR code to reconnect.
    """
    instance_name = f"rep_{current_user.id}"
    try:
        await evo_client.logout_instance(instance_name)
    except Exception as exc:
        logger.warning("Logout instance %s encountered: %s", instance_name, exc)
    return {"status": "success", "message": "WhatsApp disconnected successfully"}


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
