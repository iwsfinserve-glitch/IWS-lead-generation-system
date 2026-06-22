"""
Report routes — AI-powered lead journey and team performance reports as .docx downloads.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.base import User, Lead, LeadTimeline
from app.api.dependencies import get_current_user, require_roles

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/lead-journey/{lead_id}")
async def lead_journey_report(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate an AI-powered lead journey report as a .docx download."""
    lead_result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = lead_result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if current_user.role.value == "sales_rep" and lead.assigned_rep_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only access reports for your assigned leads")

    timeline_result = await db.execute(
        select(LeadTimeline)
        .where(LeadTimeline.lead_id == lead_id)
        .order_by(LeadTimeline.created_at.asc())
    )
    entries = timeline_result.scalars().all()

    timeline_data = [
        {
            "event_type": e.event_type,
            "metadata": e.event_metadata,
            "created_at": e.created_at.isoformat(),
        }
        for e in entries
    ]

    from app.services.ai_report_generator import generate_lead_journey_report, build_docx_report

    ai_summary = await generate_lead_journey_report(timeline_data, lead.name)
    docx_buffer = build_docx_report(f"Lead Journey Report — {lead.name}", ai_summary)

    return StreamingResponse(
        docx_buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=lead_journey_{lead_id}.docx"},
    )


@router.get("/team-performance")
async def team_performance_report(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
):
    """Generate an AI-powered team performance report as a .docx download. Admin/Manager only."""
    from app.db.base import Appointment, Task as TaskModel

    users_result = await db.execute(select(User).order_by(User.id))
    users = users_result.scalars().all()

    metrics = {}
    for user in users:
        leads_count = await db.execute(
            select(func.count()).select_from(Lead).where(Lead.assigned_rep_id == user.id)
        )
        appts_count = await db.execute(
            select(func.count()).select_from(Appointment).where(Appointment.user_id == user.id)
        )
        tasks_done = await db.execute(
            select(func.count()).select_from(TaskModel)
            .where(TaskModel.user_id == user.id, TaskModel.status == "completed")
        )
        metrics[user.name] = {
            "role": user.role.value,
            "assigned_leads": leads_count.scalar() or 0,
            "appointments": appts_count.scalar() or 0,
            "tasks_completed": tasks_done.scalar() or 0,
        }

    from app.services.ai_report_generator import generate_team_performance_report, build_docx_report

    ai_summary = await generate_team_performance_report(metrics)
    docx_buffer = build_docx_report("Team Performance Digest", ai_summary)

    return StreamingResponse(
        docx_buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=team_performance.docx"},
    )
