"""
Lead Update Request routes — create, list, approve/reject.

Sales reps submit a request to change contact-info fields on their assigned
leads (email, phone, address, DOB, source).  The rep's manager receives a
notification and can approve (which applies the changes and writes a timeline
entry) or reject (which leaves the lead unchanged).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.base import User, Lead
from app.models.lead import LeadSource
from app.models.interaction import LeadTimeline, LeadUpdateRequest
from app.schemas.lead_update_request import (
    LeadUpdateRequestCreate,
    LeadUpdateRequestRead,
    LeadUpdateRequestUpdate,
)
from app.api.dependencies import get_current_user
from app.services.notification_service import create_notification

router = APIRouter(prefix="/lead-update-requests", tags=["Lead Update Requests"])


@router.post("/", response_model=LeadUpdateRequestRead, status_code=status.HTTP_201_CREATED)
async def create_lead_update_request(
    payload: LeadUpdateRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a request to update contact-info fields on a lead.

    Only the lead's assigned sales rep can create this request.
    The rep must have a manager_id set on their account.
    Only one pending request per lead is allowed at a time.
    """
    # Fetch the lead
    lead_result = await db.execute(select(Lead).where(Lead.id == payload.lead_id))
    lead = lead_result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Only the assigned rep
    if lead.assigned_rep_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the lead's assigned sales rep can request field updates",
        )

    # Must have a manager
    if current_user.manager_id is None:
        raise HTTPException(
            status_code=400,
            detail="You don't have a manager assigned. Ask an admin to link your account to a manager before submitting update requests.",
        )

    # At least one proposed field must be provided
    proposed_fields = {
        "email": payload.proposed_email,
        "phone": payload.proposed_phone,
        "address": payload.proposed_address,
        "dob": payload.proposed_dob,
        "source_id": payload.proposed_source_id,
    }
    if all(v is None for v in proposed_fields.values()):
        raise HTTPException(
            status_code=422,
            detail="At least one field to update must be provided (email, phone, address, dob, or source)",
        )

    # Validate proposed source exists if provided
    if payload.proposed_source_id is not None:
        src_res = await db.execute(select(LeadSource).where(LeadSource.id == payload.proposed_source_id))
        if not src_res.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Proposed source not found")

    # Block duplicate pending requests for the same lead
    existing = await db.execute(
        select(LeadUpdateRequest).where(
            LeadUpdateRequest.lead_id == payload.lead_id,
            LeadUpdateRequest.status == "pending",
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="A pending update request already exists for this lead",
        )

    req = LeadUpdateRequest(
        lead_id=payload.lead_id,
        requested_by_id=current_user.id,
        manager_id=current_user.manager_id,
        # Proposed values
        proposed_email=payload.proposed_email,
        proposed_phone=payload.proposed_phone,
        proposed_address=payload.proposed_address,
        proposed_dob=payload.proposed_dob,
        proposed_source_id=payload.proposed_source_id,
        # Current snapshot
        current_email=lead.email,
        current_phone=lead.phone_number,
        current_address=lead.address,
        current_dob=lead.dob,
        current_source_id=lead.source_id,
        reason=payload.reason,
    )
    db.add(req)
    await db.flush()  # get req.id before commit

    # Notify the manager
    changed_fields = [k for k, v in proposed_fields.items() if v is not None]
    fields_str = ", ".join(changed_fields)
    notif = await create_notification(
        db,
        user_id=current_user.manager_id,
        title=f"Lead Update Request: {lead.name}",
        message=(
            f"{current_user.name} requested to update [{fields_str}] "
            f"for lead \"{lead.name}\". Reason: {payload.reason}"
        ),
        notification_type="Leads",
        link_type="lead_update_request",
        link_id=req.id,
    )

    await db.commit()
    await db.refresh(req)
    return LeadUpdateRequestRead.from_orm_request(req)


@router.get("/", response_model=list[LeadUpdateRequestRead])
async def list_lead_update_requests(
    req_status: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List lead update requests.

    - Managers/admins see requests where they are the manager.
    - Sales reps see only requests they submitted.
    """
    query = select(LeadUpdateRequest)

    if current_user.is_sales_rep:
        query = query.where(LeadUpdateRequest.requested_by_id == current_user.id)
    else:
        query = query.where(LeadUpdateRequest.manager_id == current_user.id)

    if req_status:
        query = query.where(LeadUpdateRequest.status == req_status)

    query = query.order_by(LeadUpdateRequest.created_at.desc())
    result = await db.execute(query)
    return [LeadUpdateRequestRead.from_orm_request(r) for r in result.scalars().all()]


@router.patch("/{request_id}", response_model=LeadUpdateRequestRead)
async def update_lead_update_request(
    request_id: int,
    payload: LeadUpdateRequestUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve or reject a lead update request. Manager/admin only."""
    if not current_user.is_manager_or_above:
        raise HTTPException(
            status_code=403,
            detail="Only managers or admins can approve/reject lead update requests",
        )

    result = await db.execute(
        select(LeadUpdateRequest).where(LeadUpdateRequest.id == request_id)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    # Only the assigned manager (or any admin) can resolve
    if current_user.role.value not in ("admin",) and req.manager_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the rep's assigned manager can resolve this request",
        )

    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request already {req.status}")

    req.status = payload.status
    req.resolved_at = datetime.now(timezone.utc)
    lead_name = req.lead.name if req.lead else f"Lead #{req.lead_id}"

    if payload.status == "approved":
        # Apply the proposed changes to the lead
        lead_result = await db.execute(select(Lead).where(Lead.id == req.lead_id))
        lead = lead_result.scalar_one_or_none()
        if lead:
            diff = {}
            if req.proposed_email is not None:
                diff["email"] = {"from": lead.email, "to": req.proposed_email}
                lead.email = req.proposed_email
            if req.proposed_phone is not None:
                diff["phone"] = {"from": lead.phone_number, "to": req.proposed_phone}
                lead.phone_number = req.proposed_phone
            if req.proposed_address is not None:
                diff["address"] = {"from": lead.address, "to": req.proposed_address}
                lead.address = req.proposed_address
            if req.proposed_dob is not None:
                diff["dob"] = {
                    "from": lead.dob.isoformat() if lead.dob else None,
                    "to": req.proposed_dob.isoformat(),
                }
                lead.dob = req.proposed_dob
            if req.proposed_source_id is not None:
                diff["source_id"] = {"from": lead.source_id, "to": req.proposed_source_id}
                lead.source_id = req.proposed_source_id

            # Write a timeline entry recording the approved changes
            db.add(LeadTimeline(
                lead_id=lead.id,
                user_id=req.requested_by_id,
                event_type="lead_updated",
                event_metadata={
                    "approved_by": current_user.name,
                    "requested_by": req.requester.name if req.requester else None,
                    "changes": diff,
                    "reason": req.reason,
                },
            ))

        await create_notification(
            db,
            user_id=req.requested_by_id,
            title=f"Lead Update Approved: {lead_name}",
            notification_type="Leads",
            message=(
                f'Your update request for "{lead_name}" has been '
                f"approved by {current_user.name}. The lead has been updated."
            ),
            link_type="lead",
            link_id=req.lead_id,
        )
    else:
        await create_notification(
            db,
            user_id=req.requested_by_id,
            title=f"Lead Update Rejected: {lead_name}",
            notification_type="Leads",
            message=(
                f'Your update request for "{lead_name}" has been '
                f"rejected by {current_user.name}."
            ),
            link_type="lead",
            link_id=req.lead_id,
        )

    await db.commit()
    await db.refresh(req)
    return LeadUpdateRequestRead.from_orm_request(req)
