"""
Lead routes — CRUD with RBAC filtering and automatic timeline logging.

Additional routes (SEO workflow):
    POST /public/web-lead        — public intake for SEO/website form submissions
    PATCH /{lead_id}/claim       — atomic race-condition-safe lead claiming
"""

from fastapi import APIRouter, Depends, HTTPException, Header, Query, status, BackgroundTasks
from sqlalchemy import select, or_, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.base import User, Lead, LeadSource, LeadTimeline
from app.models.enums import LeadStatus
from app.schemas.lead import (
    LeadCreate, LeadRead, LeadUpdate,
    LeadTimelineCreate, LeadTimelineRead,
    WebLeadCreate,
)
from app.api.dependencies import get_current_user, require_roles
from app.services.ai_sync import trigger_ai_analysis_background
from app.services.notification_service import notify_sales_reps_and_managers
from app.core.config import settings

router = APIRouter(prefix="/leads", tags=["Leads"])


async def _get_lead_or_404(lead_id: int, db: AsyncSession) -> Lead:
    """Fetch a lead by ID or raise 404."""
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


def _check_lead_read_access(lead: Lead, user: User) -> None:
    """All authenticated CRM users can view lead details and timeline history."""
    return


def _check_lead_write_access(lead: Lead, user: User) -> None:
    """Sales reps can only update or add notes to their own assigned leads."""
    if user.role.value == "sales_rep":
        if lead.assigned_rep_id != user.id:
            raise HTTPException(
                status_code=403, detail="You can only modify your assigned leads"
            )


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


@router.get("/summary")
async def get_leads_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return optimized status counts without loading full lead objects."""
    result = await db.execute(
        select(
            Lead.status,
            func.count(Lead.id).label("count"),
        ).group_by(Lead.status)
    )
    counts = {row.status.value: row.count for row in result.all()}

    total = sum(counts.values())
    return {
        "total": total,
        "unassigned": counts.get("unassigned", 0),
        "in_progress": counts.get("in_progress", 0),
        "potential": counts.get("potential", 0),
        "non_potential": counts.get("non_potential", 0),
        "converted_to_investor": counts.get("converted_to_investor", 0),
        "existing_investor": counts.get("existing_investor", 0),
    }


@router.post("/", response_model=LeadRead, status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: LeadCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager", "sales_rep")),
):
    """Create a new lead and log it to the timeline."""
    if payload.source_id:
        src = await db.execute(select(LeadSource).where(LeadSource.id == payload.source_id))
        if not src.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Source not found")

    lead_data = payload.model_dump(exclude={"note"})
    if current_user.role.value == "sales_rep":
        if lead_data.get("assigned_rep_id") and lead_data["assigned_rep_id"] != current_user.id:
            raise HTTPException(status_code=403, detail="Sales reps can only assign leads to themselves")
        lead_data["assigned_rep_id"] = current_user.id
        
    if lead_data.get("assigned_rep_id"):
        lead_data["status"] = LeadStatus.in_progress

    lead = Lead(**lead_data)
    db.add(lead)
    await db.flush()

    metadata = {"created_by": current_user.name, "lead_name": lead.name}
    if payload.note and payload.note.strip():
        metadata["note"] = payload.note.strip()

    timeline_entry = LeadTimeline(
        lead_id=lead.id,
        user_id=current_user.id,
        event_type="lead_created",
        event_metadata=metadata,
    )
    db.add(timeline_entry)

    if payload.note and payload.note.strip():
        note_entry = LeadTimeline(
            lead_id=lead.id,
            user_id=current_user.id,
            event_type="note",
            event_metadata={"note": payload.note.strip(), "added_by": current_user.name},
        )
        db.add(note_entry)

    background_tasks.add_task(trigger_ai_analysis_background, lead.id)
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
    _check_lead_read_access(lead, current_user)
    return LeadRead.from_orm_lead(lead)


@router.patch("/{lead_id}", response_model=LeadRead)
async def update_lead(
    lead_id: int,
    payload: LeadUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a lead. Auto-logs status changes to the timeline.

    Manager/admin assigning an unassigned lead automatically transitions
    its status to 'in_progress'.
    """
    lead = await _get_lead_or_404(lead_id, db)
    _check_lead_write_access(lead, current_user)

    update_data = payload.model_dump(exclude_unset=True)
    old_status = lead.status

    # Auto-transition: if a manager/admin assigns an unassigned lead, move to in_progress.
    if (
        "assigned_rep_id" in update_data
        and update_data["assigned_rep_id"] is not None
        and lead.status == LeadStatus.unassigned
        and "status" not in update_data
    ):
        update_data["status"] = LeadStatus.in_progress

    for field, value in update_data.items():
        setattr(lead, field, value)

    if "status" in update_data and update_data["status"] != old_status:
        timeline_entry = LeadTimeline(
            lead_id=lead.id,
            user_id=current_user.id,
            event_type="status_change",
            event_metadata={
                "old_status": old_status.value if old_status else None,
                "new_status": update_data["status"].value if hasattr(update_data["status"], "value") else update_data["status"],
                "changed_by": current_user.name,
            },
        )
        db.add(timeline_entry)
        background_tasks.add_task(trigger_ai_analysis_background, lead.id)

    await db.commit()
    await db.refresh(lead)
    return LeadRead.from_orm_lead(lead)


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    """Delete a lead. Admin only."""
    lead = await _get_lead_or_404(lead_id, db)
    await db.delete(lead)
    await db.commit()
    return None


@router.get("/{lead_id}/timeline", response_model=list[LeadTimelineRead])
async def get_lead_timeline(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the full audit timeline for a lead."""
    lead = await _get_lead_or_404(lead_id, db)
    _check_lead_read_access(lead, current_user)

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
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually add a note or event to a lead's timeline."""
    lead = await _get_lead_or_404(lead_id, db)
    _check_lead_write_access(lead, current_user)

    entry = LeadTimeline(
        lead_id=lead_id,
        user_id=current_user.id,
        event_type=payload.event_type,
        event_metadata=payload.event_metadata,
    )
    db.add(entry)
    background_tasks.add_task(trigger_ai_analysis_background, lead_id)
    await db.commit()
    await db.refresh(entry)
    return LeadTimelineRead.from_orm_timeline(entry)


@router.post("/rollover", status_code=status.HTTP_200_OK)
async def trigger_rollover(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    """Manually trigger the monthly rollover (admin only).

    Converts all 'converted_to_investor' leads to 'existing_investor'
    and logs a status_change timeline entry for each.
    """
    from app.services.rollover import run_monthly_rollover

    count = await run_monthly_rollover(db)
    return {"rolled_over": count}


# ═══════════════════════════════════════════════════════════════════════
# SEO WORKFLOW: Public Intake + Atomic Claiming
# ═══════════════════════════════════════════════════════════════════════

@router.post("/public/web-lead", response_model=LeadRead, status_code=status.HTTP_201_CREATED)
async def public_web_lead(
    payload: WebLeadCreate,
    background_tasks: BackgroundTasks,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint for SEO / website contact form submissions.

    Authenticated solely by the X-API-Key header (validated against
    settings.SEO_WEB_API_KEY — no JWT required, no user session).

    The lead is created with status='unassigned' and assigned_rep_id=None
    so any sales rep or manager can claim or assign it. A high-priority
    notification is dispatched to all sales reps and managers immediately.
    """
    # ── Key validation — fail closed ────────────────────────────────────
    if x_api_key != settings.SEO_WEB_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key.",
        )

    # ── Resolve or create the SEO lead source ────────────────────────────
    src_result = await db.execute(
        select(LeadSource).where(LeadSource.name == "SEO")
    )
    seo_source = src_result.scalar_one_or_none()
    if seo_source is None:
        seo_source = LeadSource(name="SEO", priority="high")
        db.add(seo_source)
        await db.flush()

    # ── Create the lead ──────────────────────────────────────────────────
    lead = Lead(
        name=payload.name,
        email=payload.email,
        phone_number=payload.phone_number,
        profession=payload.profession,
        address=payload.address,
        source_id=seo_source.id,
        status=LeadStatus.unassigned,
        assigned_rep_id=None,
    )
    db.add(lead)
    await db.flush()

    # ── Timeline: lead_created event ─────────────────────────────────────
    created_meta: dict = {"created_by": "SEO Web Form", "lead_name": lead.name}
    if payload.message and payload.message.strip():
        created_meta["note"] = payload.message.strip()

    db.add(LeadTimeline(
        lead_id=lead.id,
        user_id=None,
        event_type="lead_created",
        event_metadata=created_meta,
    ))

    # ── Timeline: initial note from web form message ─────────────────────
    if payload.message and payload.message.strip():
        db.add(LeadTimeline(
            lead_id=lead.id,
            user_id=None,
            event_type="note",
            event_metadata={"note": payload.message.strip(), "added_by": "SEO Web Form"},
        ))

    # ── High-priority notification to sales reps & managers ──────────────
    await notify_sales_reps_and_managers(
        db,
        title=f"New SEO Lead: {lead.name}",
        message=(
            f"A new high-priority lead from the SEO web form has arrived and is unassigned. "
            f"Name: {lead.name}. Click to view and claim."
        ),
        notification_type="Leads",
        link_type="lead",
        link_id=lead.id,
    )

    # ── Trigger background AI scoring ────────────────────────────────────
    background_tasks.add_task(trigger_ai_analysis_background, lead.id)

    await db.commit()
    await db.refresh(lead)
    return LeadRead.from_orm_lead(lead)


@router.patch("/{lead_id}/claim", response_model=LeadRead)
async def claim_lead(
    lead_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("sales_rep", "manager")),
):
    """Atomically claim an unassigned lead.

    Uses a conditional UPDATE (WHERE assigned_rep_id IS NULL AND status = 'unassigned')
    so that if two reps click 'Claim' simultaneously, exactly one wins and the other
    receives a 409 Conflict — no double-assignment is possible.

    Sets status to 'in_progress' and assigned_rep_id to the calling user.
    """
    # Atomic conditional update — only succeeds if lead is still unassigned
    result = await db.execute(
        update(Lead)
        .where(
            Lead.id == lead_id,
            Lead.assigned_rep_id.is_(None),
            Lead.status == LeadStatus.unassigned,
        )
        .values(
            assigned_rep_id=current_user.id,
            status=LeadStatus.in_progress,
        )
        .execution_options(synchronize_session=False)
    )

    if result.rowcount == 0:
        # Either lead doesn't exist or was already claimed — check which
        check = await db.execute(select(Lead).where(Lead.id == lead_id))
        if not check.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Lead not found")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This lead has already been claimed or assigned to another representative.",
        )

    # Fetch the freshly updated lead
    lead = await _get_lead_or_404(lead_id, db)

    # Log claim event to timeline
    db.add(LeadTimeline(
        lead_id=lead.id,
        user_id=current_user.id,
        event_type="lead_assigned",
        event_metadata={
            "assigned_to": current_user.name,
            "assigned_to_id": current_user.id,
            "method": "self_claim",
        },
    ))
    db.add(LeadTimeline(
        lead_id=lead.id,
        user_id=current_user.id,
        event_type="status_change",
        event_metadata={
            "old_status": LeadStatus.unassigned.value,
            "new_status": LeadStatus.in_progress.value,
            "changed_by": current_user.name,
        },
    ))

    background_tasks.add_task(trigger_ai_analysis_background, lead.id)
    await db.commit()
    await db.refresh(lead)
    return LeadRead.from_orm_lead(lead)

