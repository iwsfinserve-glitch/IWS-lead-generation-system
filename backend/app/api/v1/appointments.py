"""
Appointment routes — CRUD with timeline logging and background Google Calendar sync.
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.base import User, Lead, Appointment, LeadTimeline
from app.schemas.appointment import AppointmentCreate, AppointmentRead, AppointmentUpdate
from app.api.dependencies import get_current_user

router = APIRouter(prefix="/appointments", tags=["Appointments"])


@router.get("/", response_model=list[AppointmentRead])
async def list_appointments(
    lead_id: int | None = None,
    user_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List appointments. Sales reps see only their own."""
    query = select(Appointment)
    if current_user.role.value == "sales_rep":
        query = query.where(Appointment.user_id == current_user.id)
    elif user_id is not None:
        query = query.where(Appointment.user_id == user_id)
    if lead_id:
        query = query.where(Appointment.lead_id == lead_id)
    query = query.order_by(Appointment.start_time.desc())
    result = await db.execute(query)
    return [AppointmentRead.from_orm_appointment(a) for a in result.scalars().all()]


@router.post("/", response_model=AppointmentRead, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    payload: AppointmentCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create appointment, log to timeline, push to Google Calendar in background."""
    lead_result = await db.execute(select(Lead).where(Lead.id == payload.lead_id))
    lead = lead_result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if current_user.role.value == "sales_rep" and lead.assigned_rep_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only book appointments for your assigned leads")

    appointment = Appointment(
        lead_id=payload.lead_id, user_id=current_user.id, title=payload.title,
        note=payload.note, mode=payload.mode, location=payload.location,
        start_time=payload.start_time, end_time=payload.end_time,
    )
    db.add(appointment)
    await db.flush()

    db.add(LeadTimeline(
        lead_id=payload.lead_id, user_id=current_user.id,
        event_type="appointment_booked",
        event_metadata={
            "appointment_id": appointment.id, "title": appointment.title,
            "mode": appointment.mode.value,
            "start_time": appointment.start_time.isoformat(),
            "end_time": appointment.end_time.isoformat(),
        },
    ))
    await db.commit()
    await db.refresh(appointment)

    if current_user.google_refresh_token:
        from app.services.google_sync import sync_appointment_to_calendar
        background_tasks.add_task(sync_appointment_to_calendar, current_user, appointment, "create")

    return AppointmentRead.from_orm_appointment(appointment)


@router.patch("/{appointment_id}", response_model=AppointmentRead)
async def update_appointment(
    appointment_id: int, payload: AppointmentUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update appointment, log changes to timeline, sync to Google Calendar."""
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    appointment = result.scalar_one_or_none()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if current_user.role.value == "sales_rep" and appointment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own appointments")

    update_data = payload.model_dump(exclude_unset=True)
    changes = {}
    for field, value in update_data.items():
        old_val = getattr(appointment, field)
        if old_val != value:
            changes[field] = {"old": str(old_val), "new": str(value)}
        setattr(appointment, field, value)

    if changes:
        db.add(LeadTimeline(
            lead_id=appointment.lead_id, user_id=current_user.id,
            event_type="appointment_updated",
            event_metadata={"appointment_id": appointment.id, "changes": changes},
        ))

    await db.commit()
    await db.refresh(appointment)

    if current_user.google_refresh_token and appointment.google_event_id:
        from app.services.google_sync import sync_appointment_to_calendar
        background_tasks.add_task(sync_appointment_to_calendar, current_user, appointment, "update")

    return AppointmentRead.from_orm_appointment(appointment)


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_appointment(
    appointment_id: int, background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete appointment, log to timeline, remove from Google Calendar."""
    result = await db.execute(select(Appointment).where(Appointment.id == appointment_id))
    appointment = result.scalar_one_or_none()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if current_user.role.value == "sales_rep" and appointment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own appointments")

    db.add(LeadTimeline(
        lead_id=appointment.lead_id, user_id=current_user.id,
        event_type="appointment_cancelled",
        event_metadata={"appointment_id": appointment.id, "title": appointment.title},
    ))
    google_event_id = appointment.google_event_id
    await db.delete(appointment)
    await db.commit()

    if current_user.google_refresh_token and google_event_id:
        from app.services.google_sync import delete_calendar_event
        background_tasks.add_task(delete_calendar_event, current_user, google_event_id)
