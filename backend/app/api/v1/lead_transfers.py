"""
Lead Transfer Request routes — create, list, approve/reject.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.base import User, Lead
from app.models.interaction import LeadTransferRequest
from app.schemas.lead_transfer import (
    LeadTransferRequestCreate,
    LeadTransferRequestRead,
    LeadTransferRequestUpdate,
)
from app.api.dependencies import get_current_user
from app.services.notification_service import create_notification, notify_managers

router = APIRouter(prefix="/lead-transfer-requests", tags=["Lead Transfer Requests"])


@router.post("/", response_model=LeadTransferRequestRead, status_code=status.HTTP_201_CREATED)
async def create_lead_transfer_request(
    payload: LeadTransferRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a lead transfer request.

    The requesting user must be the lead's currently assigned rep.
    A notification is sent to all managers and admins.
    """
    # Fetch the lead
    result = await db.execute(select(Lead).where(Lead.id == payload.lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Only the assigned rep can request a transfer
    if lead.assigned_rep_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only the assigned rep can request a lead transfer",
        )

    # Cannot transfer to yourself
    if payload.to_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot transfer a lead to yourself")

    # Verify target user exists
    target_result = await db.execute(select(User).where(User.id == payload.to_user_id))
    target_user = target_result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")

    # Check for existing pending request on this lead
    existing = await db.execute(
        select(LeadTransferRequest).where(
            LeadTransferRequest.lead_id == payload.lead_id,
            LeadTransferRequest.status == "pending",
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="A pending transfer request already exists for this lead",
        )

    req = LeadTransferRequest(
        lead_id=payload.lead_id,
        from_user_id=current_user.id,
        to_user_id=payload.to_user_id,
        reason=payload.reason,
    )
    db.add(req)

    # Notify all managers and admins
    await notify_managers(
        db,
        title="Lead Transfer Request",
        message=(
            f'{current_user.name} requested to transfer lead '
            f'"{lead.name}" to {target_user.name}'
        ),
        notification_type="Leads",
        link_type="lead",
        link_id=lead.id,
    )

    await db.commit()
    await db.refresh(req)

    return LeadTransferRequestRead.from_orm_request(req)


@router.get("/", response_model=list[LeadTransferRequestRead])
async def list_lead_transfer_requests(
    req_status: str | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List lead transfer requests.

    - Managers/admins see all requests.
    - Sales reps see only requests they submitted.
    """
    query = select(LeadTransferRequest)

    if current_user.is_sales_rep:
        query = query.where(LeadTransferRequest.from_user_id == current_user.id)

    if req_status:
        query = query.where(LeadTransferRequest.status == req_status)

    query = query.order_by(LeadTransferRequest.created_at.desc())
    result = await db.execute(query)
    return [LeadTransferRequestRead.from_orm_request(r) for r in result.scalars().all()]


@router.patch("/{request_id}", response_model=LeadTransferRequestRead)
async def update_lead_transfer_request(
    request_id: int,
    payload: LeadTransferRequestUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve or reject a lead transfer request. Manager/admin only."""
    if not current_user.is_manager_or_above:
        raise HTTPException(
            status_code=403,
            detail="Only managers or admins can approve/reject transfer requests",
        )

    result = await db.execute(
        select(LeadTransferRequest).where(LeadTransferRequest.id == request_id)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Transfer request not found")

    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request already {req.status}")

    req.status = payload.status
    lead_name = req.lead.name if req.lead else f"Lead #{req.lead_id}"

    if payload.status == "approved":
        # Reassign the lead
        lead_result = await db.execute(select(Lead).where(Lead.id == req.lead_id))
        lead = lead_result.scalar_one_or_none()
        if lead:
            lead.assigned_rep_id = req.to_user_id

        # Notify the requesting rep (from_user)
        await create_notification(
            db,
            user_id=req.from_user_id,
            title="Lead Transfer Approved",
            notification_type="Leads",
            message=(
                f'Your transfer request for "{lead_name}" has been '
                f'approved by {current_user.name}. The lead is now assigned to '
                f'{req.to_user.name if req.to_user else "the new rep"}.'
            ),
            link_type="lead",
            link_id=req.lead_id,
        )

        # Notify the target rep (to_user)
        await create_notification(
            db,
            user_id=req.to_user_id,
            title="Lead Transferred to You",
            notification_type="Leads",
            message=(
                f'Lead "{lead_name}" has been transferred to you from '
                f'{req.from_user.name if req.from_user else "another rep"}. '
                f'Approved by {current_user.name}.'
            ),
            link_type="lead",
            link_id=req.lead_id,
        )

    else:
        # Rejected — notify only the requesting rep
        await create_notification(
            db,
            user_id=req.from_user_id,
            title="Lead Transfer Rejected",
            notification_type="Leads",
            message=(
                f'Your transfer request for "{lead_name}" has been '
                f'rejected by {current_user.name}.'
            ),
            link_type="lead",
            link_id=req.lead_id,
        )

    await db.commit()
    await db.refresh(req)

    return LeadTransferRequestRead.from_orm_request(req)
