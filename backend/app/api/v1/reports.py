"""
Report routes — AI-powered reports (JSON preview + .docx download).

Endpoint pairs (JSON + download):
    GET /reports/lead-journey/{id}           → JSON preview
    GET /reports/lead-journey/{id}/download  → .docx
    GET /reports/leads-periodic              → JSON preview
    GET /reports/leads-periodic/download     → .docx
    GET /reports/user-performance/{id}       → JSON preview (manager/admin)
    GET /reports/user-performance/{id}/download → .docx
    GET /reports/team-performance            → JSON preview (manager/admin)
    GET /reports/team-performance/download   → .docx

RBAC:
    sales_rep  → own leads journey, own periodic portfolio
    manager    → above + subordinates periodic/performance + team digest
    admin      → all of the above for any user/manager
"""

from datetime import date, datetime, timezone
from typing import Optional
import base64

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, case, literal_column, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.base import User, Lead, LeadTimeline, Appointment, Task as TaskModel, LeadSource
from app.models.enums import UserRole
from app.api.dependencies import get_current_user, require_roles
from app.services.ai_report_generator import (
    generate_lead_journey_report,
    generate_periodic_leads_report,
    generate_user_performance_report,
    generate_team_performance_report,
    build_docx_report,
    AIReportError,
)

router = APIRouter(prefix="/reports", tags=["Reports"])


# ── Helpers ──────────────────────────────────────────────────────────────────

def _tz(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _period_label(start_date: Optional[date], end_date: Optional[date], period: str) -> str:
    if period and period != "Custom":
        return period
    if start_date and end_date:
        return f"{start_date.isoformat()} to {end_date.isoformat()}"
    return "All Time"


async def _get_lead_or_404(lead_id: int, db: AsyncSession) -> Lead:
    r = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = r.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


async def _get_user_or_404(user_id: int, db: AsyncSession) -> User:
    r = await db.execute(select(User).where(User.id == user_id))
    user = r.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _check_rep_rbac(target_rep: User, current_user: User) -> None:
    """Manager can only view their direct subordinates. Admin can view anyone."""
    role = current_user.role
    if role == UserRole.admin:
        return
    if role == UserRole.manager:
        if target_rep.manager_id != current_user.id and target_rep.id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only view reports for your subordinates")
        return
    raise HTTPException(status_code=403, detail="Insufficient permissions")


def _build_lead_date_filter(start_date, end_date):
    """Build SQLAlchemy filters for Lead.created_at within date range."""
    filters = []
    if start_date:
        filters.append(Lead.created_at >= datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc))
    if end_date:
        filters.append(Lead.created_at <= datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc))
    return filters


async def _build_periodic_leads_summary(leads: list) -> dict:
    """Build metrics dict from a list of Lead ORM objects."""
    by_status: dict = {}
    by_source: dict = {}
    leads_list = []

    for lead in leads:
        status = lead.status.value if hasattr(lead.status, "value") else str(lead.status)
        source_name = lead.source.name if lead.source else "Unknown"
        by_status[status] = by_status.get(status, 0) + 1
        by_source[source_name] = by_source.get(source_name, 0) + 1

        # Build timeline events count
        timeline_count = len(lead.timeline) if lead.timeline else 0

        leads_list.append({
            "id": lead.id,
            "name": lead.name,
            "profession": lead.profession,
            "status": status,
            "source": source_name,
            "created_at": lead.created_at.date().isoformat() if lead.created_at else None,
            "ai_score": lead.ai_score,
            "ai_score_label": lead.ai_score_label,
            "timeline_count": timeline_count,
            "last_contact": lead.last_contact.isoformat() if lead.last_contact else None,
        })

    total = len(leads)
    converted = by_status.get("converted_to_investor", 0) + by_status.get("existing_investor", 0)

    return {
        "total_leads": total,
        "converted_leads": converted,
        "conversion_rate": round(converted / total * 100, 1) if total else 0,
        "by_status": by_status,
        "by_source": by_source,
        "leads": leads_list,
    }


async def _build_user_performance_metrics(
    target_user: User, db: AsyncSession,
    start_date: Optional[date], end_date: Optional[date]
) -> dict:
    """Aggregate performance metrics for a single user within date range."""
    date_filters = _build_lead_date_filter(start_date, end_date)

    # Leads assigned to this user
    leads_q = select(Lead).where(Lead.assigned_rep_id == target_user.id)
    if date_filters:
        leads_q = leads_q.where(and_(*date_filters))
    leads_result = await db.execute(leads_q)
    leads = leads_result.scalars().all()

    by_status: dict = {}
    for l in leads:
        s = l.status.value if hasattr(l.status, "value") else str(l.status)
        by_status[s] = by_status.get(s, 0) + 1

    total_leads = len(leads)
    converted = by_status.get("converted_to_investor", 0) + by_status.get("existing_investor", 0)

    # Appointments
    appt_q = select(func.count()).select_from(Appointment).where(Appointment.user_id == target_user.id)
    if start_date:
        appt_q = appt_q.where(Appointment.start_time >= datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc))
    if end_date:
        appt_q = appt_q.where(Appointment.start_time <= datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc))
    appt_count = (await db.execute(appt_q)).scalar() or 0

    # Tasks
    task_q = select(TaskModel).where(TaskModel.user_id == target_user.id)
    if start_date:
        task_q = task_q.where(TaskModel.assigned_on >= datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc))
    if end_date:
        task_q = task_q.where(TaskModel.assigned_on <= datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc))
    task_result = await db.execute(task_q)
    tasks = task_result.scalars().all()
    total_tasks = len(tasks)
    tasks_completed = sum(1 for t in tasks if t.status == "completed")

    # Timeline interactions
    tl_q = select(func.count()).select_from(LeadTimeline).where(LeadTimeline.user_id == target_user.id)
    if start_date:
        tl_q = tl_q.where(LeadTimeline.created_at >= datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc))
    if end_date:
        tl_q = tl_q.where(LeadTimeline.created_at <= datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc))
    interaction_count = (await db.execute(tl_q)).scalar() or 0

    return {
        "user_name": target_user.name,
        "user_role": target_user.role.value,
        "email": target_user.email,
        "total_leads_assigned": total_leads,
        "by_status": by_status,
        "converted_leads": converted,
        "conversion_rate": round(converted / total_leads * 100, 1) if total_leads else 0,
        "total_appointments": appt_count,
        "total_tasks": total_tasks,
        "tasks_completed": tasks_completed,
        "task_completion_rate": round(tasks_completed / total_tasks * 100, 1) if total_tasks else 0,
        "total_interactions": interaction_count,
    }


# ── Lead Journey Report ───────────────────────────────────────────────────────

async def _lead_journey_data(lead_id: int, current_user: User, db: AsyncSession) -> dict:
    lead = await _get_lead_or_404(lead_id, db)
    if current_user.role == UserRole.sales_rep and lead.assigned_rep_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only access reports for your assigned leads")

    timeline_result = await db.execute(
        select(LeadTimeline).where(LeadTimeline.lead_id == lead_id).order_by(LeadTimeline.created_at.asc())
    )
    entries = timeline_result.scalars().all()
    timeline_data = [
        {"event_type": e.event_type, "metadata": e.event_metadata, "created_at": e.created_at.isoformat()}
        for e in entries
    ]
    return {"lead": lead, "timeline_data": timeline_data}


@router.get("/lead-journey/{lead_id}")
async def lead_journey_report(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """JSON: AI lead journey narrative + timeline data + embedded docx_b64."""
    data = await _lead_journey_data(lead_id, current_user, db)
    lead, timeline_data = data["lead"], data["timeline_data"]
    try:
        narrative = await generate_lead_journey_report(timeline_data, lead.name)
    except AIReportError:
        raise HTTPException(status_code=503, detail="AI report generation is temporarily unavailable.")
    metrics = {
        "total_events": len(timeline_data),
        "by_event_type": {et: sum(1 for t in timeline_data if t["event_type"] == et)
                          for et in set(t["event_type"] for t in timeline_data)},
    }
    buf = build_docx_report(f"Lead Journey Report — {lead.name}", narrative, metrics, "lead_journey")
    docx_b64 = base64.b64encode(buf.read()).decode()
    return {
        "report_type": "lead_journey",
        "lead_name": lead.name,
        "lead_id": lead.id,
        "narrative": narrative,
        "timeline": timeline_data,
        "metrics": metrics,
        "docx_b64": docx_b64,
    }


@router.get("/lead-journey/{lead_id}/download")
async def lead_journey_report_download(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download: Lead journey report as .docx."""
    data = await _lead_journey_data(lead_id, current_user, db)
    lead, timeline_data = data["lead"], data["timeline_data"]
    try:
        narrative = await generate_lead_journey_report(timeline_data, lead.name)
    except AIReportError:
        raise HTTPException(status_code=503, detail="AI report generation is temporarily unavailable.")
    metrics = {
        "total_events": len(timeline_data),
        "by_event_type": {et: sum(1 for t in timeline_data if t["event_type"] == et)
                          for et in set(t["event_type"] for t in timeline_data)},
    }
    buf = build_docx_report(f"Lead Journey Report — {lead.name}", narrative, metrics, "lead_journey")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=lead_journey_{lead_id}.docx"},
    )


# ── Periodic Leads Report ─────────────────────────────────────────────────────

async def _periodic_leads_data(
    current_user: User, db: AsyncSession,
    user_id: Optional[int], start_date: Optional[date], end_date: Optional[date], period: str
) -> dict:
    """Assemble leads + metrics for the periodic report with RBAC."""
    # Determine whose leads to fetch
    if current_user.role == UserRole.sales_rep:
        target_user_id = current_user.id
        target_name = f"{current_user.name} (Sales Representative)"
    elif current_user.role == UserRole.manager:
        if user_id is None:
            # All subordinates
            sub_ids_r = await db.execute(select(User.id).where(User.manager_id == current_user.id))
            sub_ids = [r[0] for r in sub_ids_r.all()] + [current_user.id]
            target_user_id = sub_ids  # type: ignore
            target_name = f"{current_user.name}'s Team"
        else:
            target_rep = await _get_user_or_404(user_id, db)
            _check_rep_rbac(target_rep, current_user)
            target_user_id = [user_id]
            target_name = f"{target_rep.name}"
    else:  # admin
        if user_id:
            target_rep = await _get_user_or_404(user_id, db)
            target_user_id = [user_id]
            target_name = f"{target_rep.name}"
        else:
            target_user_id = None  # firm-wide
            target_name = "Firm-Wide"

    # Build query
    q = select(Lead)
    if isinstance(target_user_id, list):
        q = q.where(Lead.assigned_rep_id.in_(target_user_id))
    elif isinstance(target_user_id, int):
        q = q.where(Lead.assigned_rep_id == target_user_id)
    # else: target_user_id is None → firm-wide, no filter

    date_filters = _build_lead_date_filter(start_date, end_date)
    if date_filters:
        q = q.where(and_(*date_filters))

    result = await db.execute(q)
    leads = result.scalars().all()
    summary = await _build_periodic_leads_summary(leads)
    summary["period_label"] = _period_label(start_date, end_date, period)
    summary["target_name"] = target_name
    return summary


@router.get("/leads-periodic")
async def periodic_leads_report(
    user_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    period: str = Query("All Time"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """JSON: Periodic leads portfolio + journey report including docx_b64."""
    summary = await _periodic_leads_data(current_user, db, user_id, start_date, end_date, period)
    try:
        narrative = await generate_periodic_leads_report(
            summary, summary["period_label"], summary["target_name"]
        )
    except AIReportError:
        raise HTTPException(status_code=503, detail="AI report generation is temporarily unavailable.")
    title = f"Leads Report — {summary['target_name']} ({summary['period_label']})"
    buf = build_docx_report(title, narrative, summary, "periodic_leads")
    docx_b64 = base64.b64encode(buf.read()).decode()
    return {
        "report_type": "periodic_leads",
        "narrative": narrative,
        "metrics": summary,
        "docx_b64": docx_b64,
    }


@router.get("/leads-periodic/download")
async def periodic_leads_report_download(
    user_id: Optional[int] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    period: str = Query("All Time"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download: Periodic leads portfolio + journey report as .docx."""
    summary = await _periodic_leads_data(current_user, db, user_id, start_date, end_date, period)
    try:
        narrative = await generate_periodic_leads_report(
            summary, summary["period_label"], summary["target_name"]
        )
    except AIReportError:
        raise HTTPException(status_code=503, detail="AI report generation is temporarily unavailable.")
    title = f"Leads Report — {summary['target_name']} ({summary['period_label']})"
    buf = build_docx_report(title, narrative, summary, "periodic_leads")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=periodic_leads_report.docx"},
    )


# ── User Performance Report ───────────────────────────────────────────────────

@router.get("/user-performance/{target_user_id}")
async def user_performance_report(
    target_user_id: int,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    period: str = Query("All Time"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """JSON: Individual performance review — Manager/Admin only."""
    if current_user.role == UserRole.sales_rep:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    target_user = await _get_user_or_404(target_user_id, db)
    _check_rep_rbac(target_user, current_user)

    metrics = await _build_user_performance_metrics(target_user, db, start_date, end_date)
    period_label = _period_label(start_date, end_date, period)
    try:
        narrative = await generate_user_performance_report(
            metrics, period_label, target_user.name, target_user.role.value
        )
    except AIReportError:
        raise HTTPException(status_code=503, detail="AI report generation is temporarily unavailable.")
    title = f"Performance Review — {target_user.name} ({period_label})"
    buf = build_docx_report(title, narrative, metrics, "user_performance")
    docx_b64 = base64.b64encode(buf.read()).decode()
    return {
        "report_type": "user_performance",
        "narrative": narrative,
        "metrics": metrics,
        "period_label": period_label,
        "docx_b64": docx_b64,
    }


@router.get("/user-performance/{target_user_id}/download")
async def user_performance_report_download(
    target_user_id: int,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    period: str = Query("All Time"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download: Individual performance review as .docx."""
    if current_user.role == UserRole.sales_rep:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    target_user = await _get_user_or_404(target_user_id, db)
    _check_rep_rbac(target_user, current_user)

    metrics = await _build_user_performance_metrics(target_user, db, start_date, end_date)
    period_label = _period_label(start_date, end_date, period)
    try:
        narrative = await generate_user_performance_report(
            metrics, period_label, target_user.name, target_user.role.value
        )
    except AIReportError:
        raise HTTPException(status_code=503, detail="AI report generation is temporarily unavailable.")
    title = f"Performance Review — {target_user.name} ({period_label})"
    buf = build_docx_report(title, narrative)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=performance_{target_user_id}.docx"},
    )


# ── Team Performance Report ───────────────────────────────────────────────────

async def _team_performance_data(
    current_user: User, db: AsyncSession,
    start_date: Optional[date], end_date: Optional[date],
    manager_id: Optional[int],
) -> dict:
    """Aggregate team metrics with date range + optional manager filter."""
    # Determine scope
    if current_user.role == UserRole.manager:
        sub_ids_r = await db.execute(select(User.id).where(User.manager_id == current_user.id))
        scope_ids = [r[0] for r in sub_ids_r.all()] + [current_user.id]
        team_label = f"{current_user.name}'s Team"
    else:  # admin
        if manager_id:
            mgr = await _get_user_or_404(manager_id, db)
            sub_ids_r = await db.execute(select(User.id).where(User.manager_id == manager_id))
            scope_ids = [r[0] for r in sub_ids_r.all()] + [manager_id]
            team_label = f"{mgr.name}'s Team"
        else:
            scope_ids = None  # all users
            team_label = "Firm-Wide Team"

    # Fetch users in scope
    users_q = select(User)
    if scope_ids is not None:
        users_q = users_q.where(User.id.in_(scope_ids))
    users_result = await db.execute(users_q)
    users = users_result.scalars().all()

    date_filters = _build_lead_date_filter(start_date, end_date)

    member_metrics = []
    totals = {"total_leads": 0, "converted_leads": 0, "total_appointments": 0, "tasks_completed": 0, "total_tasks": 0}

    for u in users:
        m = await _build_user_performance_metrics(u, db, start_date, end_date)
        member_metrics.append(m)
        totals["total_leads"] += m["total_leads_assigned"]
        totals["converted_leads"] += m["converted_leads"]
        totals["total_appointments"] += m["total_appointments"]
        totals["tasks_completed"] += m["tasks_completed"]
        totals["total_tasks"] += m["total_tasks"]

    totals["avg_conversion_rate"] = (
        round(totals["converted_leads"] / totals["total_leads"] * 100, 1)
        if totals["total_leads"] else 0
    )

    return {
        "team_label": team_label,
        "member_count": len(users),
        "members": member_metrics,
        "totals": totals,
    }


@router.get("/team-performance")
async def team_performance_report(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    period: str = Query("All Time"),
    manager_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
):
    """JSON: Team performance digest including docx_b64. Admin/Manager only."""
    data = await _team_performance_data(current_user, db, start_date, end_date, manager_id)
    period_label = _period_label(start_date, end_date, period)
    metrics_for_ai = {
        "period": period_label,
        "team": data["team_label"],
        "members": data["members"],
        "totals": data["totals"],
    }
    try:
        narrative = await generate_team_performance_report(metrics_for_ai)
    except AIReportError:
        raise HTTPException(status_code=503, detail="AI report generation is temporarily unavailable.")
    title = f"Team Performance Digest — {data['team_label']} ({period_label})"
    buf = build_docx_report(title, narrative, data, "team_performance")
    docx_b64 = base64.b64encode(buf.read()).decode()
    return {
        "report_type": "team_performance",
        "narrative": narrative,
        "metrics": data,
        "period_label": period_label,
        "docx_b64": docx_b64,
    }


@router.get("/team-performance/download")
async def team_performance_report_download(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    period: str = Query("All Time"),
    manager_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
):
    """Download: Team performance digest as .docx."""
    data = await _team_performance_data(current_user, db, start_date, end_date, manager_id)
    period_label = _period_label(start_date, end_date, period)
    metrics_for_ai = {"period": period_label, "team": data["team_label"], "members": data["members"], "totals": data["totals"]}
    try:
        narrative = await generate_team_performance_report(metrics_for_ai)
    except AIReportError:
        raise HTTPException(status_code=503, detail="AI report generation is temporarily unavailable.")
    buf = build_docx_report(f"Team Performance Digest — {data['team_label']} ({period_label})", narrative)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=team_performance.docx"},
    )
