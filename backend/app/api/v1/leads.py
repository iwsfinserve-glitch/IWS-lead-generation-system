"""
Lead routes — CRUD with RBAC filtering and automatic timeline logging.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.base import User, Lead, LeadSource, LeadTimeline
from app.models.enums import LeadStatus
from app.schemas.lead import (
    LeadCreate, LeadRead, LeadUpdate,
    LeadTimelineCreate, LeadTimelineRead,
)
from app.api.dependencies import get_current_user, require_roles

router = APIRouter(prefix="/leads", tags=["Leads"])


async def _get_lead_or_404(lead_id: int, db: AsyncSession) -> Lead:
    """Fetch a lead by ID or raise 404."""
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


def _check_lead_access(lead: Lead, user: User) -> None:
    """Sales reps can only access their own assigned leads."""
    if user.role.value == "sales_rep" and lead.assigned_rep_id != user.id:
        raise HTTPException(status_code=403, detail="You can only access your assigned leads")


@router.get("/", response_model=list[LeadRead])
async def list_leads(
    status_filter: LeadStatus | None = Query(None, alias="status"),
    source_id: int | None = None,
    assigned_rep_id: int | None = None,
    search: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List leads with optional filters."""
    query = select(Lead)

    if status_filter:
        query = query.where(Lead.status == status_filter)
    if source_id:
        query = query.where(Lead.source_id == source_id)
    if assigned_rep_id:
        query = query.where(Lead.assigned_rep_id == assigned_rep_id)
    if search:
        query = query.where(
            or_(
                Lead.name.ilike(f"%{search}%"),
                Lead.email.ilike(f"%{search}%"),
                Lead.phone_number.ilike(f"%{search}%"),
            )
        )

    query = query.order_by(Lead.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    leads = result.scalars().all()
    return [LeadRead.from_orm_lead(l) for l in leads]


@router.post("/", response_model=LeadRead, status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: LeadCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
):
    """Create a new lead and log it to the timeline. Admin/Manager only."""
    if payload.source_id:
        src = await db.execute(select(LeadSource).where(LeadSource.id == payload.source_id))
        if not src.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Source not found")

    lead = Lead(**payload.model_dump())
    db.add(lead)
    await db.flush()

    timeline_entry = LeadTimeline(
        lead_id=lead.id,
        user_id=current_user.id,
        event_type="lead_created",
        event_metadata={"created_by": current_user.name, "lead_name": lead.name},
    )
    db.add(timeline_entry)

    await db.commit()
    await db.refresh(lead)
    return LeadRead.from_orm_lead(lead)


@router.get("/{lead_id}", response_model=LeadRead)
async def get_lead(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single lead with RBAC check."""
    lead = await _get_lead_or_404(lead_id, db)
    return LeadRead.from_orm_lead(lead)


@router.patch("/{lead_id}", response_model=LeadRead)
async def update_lead(
    lead_id: int,
    payload: LeadUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a lead. Auto-logs status changes to the timeline."""
    lead = await _get_lead_or_404(lead_id, db)
    _check_lead_access(lead, current_user)

    update_data = payload.model_dump(exclude_unset=True)
    old_status = lead.status

    for field, value in update_data.items():
        setattr(lead, field, value)

    if "status" in update_data and update_data["status"] != old_status:
        timeline_entry = LeadTimeline(
            lead_id=lead.id,
            user_id=current_user.id,
            event_type="status_change",
            event_metadata={
                "old_status": old_status.value,
                "new_status": update_data["status"].value,
                "changed_by": current_user.name,
            },
        )
        db.add(timeline_entry)

    await db.commit()
    await db.refresh(lead)
    return LeadRead.from_orm_lead(lead)


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    """Delete a lead (cascades to timeline and appointments). Admin only."""
    lead = await _get_lead_or_404(lead_id, db)
    await db.delete(lead)
    await db.commit()


@router.get("/{lead_id}/timeline", response_model=list[LeadTimelineRead])
async def get_lead_timeline(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the full audit timeline for a lead."""
    lead = await _get_lead_or_404(lead_id, db)

    result = await db.execute(
        select(LeadTimeline)
        .where(LeadTimeline.lead_id == lead_id)
        .order_by(LeadTimeline.created_at.desc())
    )
    entries = result.scalars().all()
    return [LeadTimelineRead.from_orm_timeline(e) for e in entries]


@router.post("/{lead_id}/timeline", response_model=LeadTimelineRead, status_code=status.HTTP_201_CREATED)
async def add_timeline_entry(
    lead_id: int,
    payload: LeadTimelineCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually add a note or event to a lead's timeline."""
    lead = await _get_lead_or_404(lead_id, db)
    _check_lead_access(lead, current_user)

    entry = LeadTimeline(
        lead_id=lead_id,
        user_id=current_user.id,
        event_type=payload.event_type,
        event_metadata=payload.event_metadata,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return LeadTimelineRead.from_orm_timeline(entry)
