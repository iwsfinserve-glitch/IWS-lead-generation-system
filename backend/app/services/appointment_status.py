"""
appointment_status.py — Background reconcile service for appointment lifecycle.

State machine (automated transitions only):
    upcoming  -> pending    when now > appointment.end_time
    pending   -> escalation when now > appointment.end_time + 7 days
                            AND manager_alerted == False
                            AND rep.manager_id is not None

Manual transitions (upcoming/pending -> completed) are handled via the
PATCH /appointments/{id} endpoint using AppointmentUpdate.status = "completed".
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interaction import Appointment, Notification
from app.db.base import User
from app.services.notification_service import create_notification

logger = logging.getLogger(__name__)

_7_DAYS = timedelta(days=7)


async def reconcile_appointment_statuses(db: AsyncSession) -> None:
    """Batch reconcile appointment statuses and fire notifications.

    Runs as a scheduled job (default every hour). Each call:
      1. Flips overdue 'upcoming' appointments to 'pending' and notifies rep.
      2. Escalates 'pending' appointments past 7 days to the rep's manager.

    Commits once at the end after all changes are queued.
    """
    now = datetime.now(timezone.utc)
    escalation_threshold = now - _7_DAYS

    # ── Query 1: upcoming -> pending ─────────────────────────────────────
    # Fetch rows (not a bulk UPDATE) so we can send per-row notifications.
    result = await db.execute(
        select(Appointment).where(
            Appointment.status == "upcoming",
            Appointment.end_time < now,
        ).execution_options(populate_existing=True)
    )
    overdue = result.scalars().all()

    for appt in overdue:
        appt.status = "pending"
        lead_name = appt.lead.name if appt.lead else f"Lead #{appt.lead_id}"
        date_str = appt.start_time.strftime("%d %b %Y, %I:%M %p")
        await create_notification(
            db,
            user_id=appt.user_id,
            title=appt.title,
            notification_type="appointment_missed",
            message=(
                f"Your appointment with {lead_name} on {date_str} "
                f"wasn't marked complete and is now pending."
            ),
            link_type="appointment",
            link_id=appt.id,
        )

    if overdue:
        logger.info(f"Reconcile: {len(overdue)} appointment(s) flipped upcoming -> pending.")

    # ── Query 2: pending + 7 days -> escalate to manager ────────────────
    result2 = await db.execute(
        select(Appointment).where(
            Appointment.status == "pending",
            Appointment.manager_alerted == False,  # noqa: E712
            Appointment.end_time < escalation_threshold,
        ).execution_options(populate_existing=True)
    )
    to_escalate = result2.scalars().all()

    for appt in to_escalate:
        appt.manager_alerted = True  # set before any await to stay idempotent

        # Load the rep to check for manager_id
        rep_result = await db.execute(select(User).where(User.id == appt.user_id))
        rep = rep_result.scalar_one_or_none()

        # Silently skip if no manager is assigned — do not error
        if not rep or not rep.manager_id:
            logger.debug(
                f"Reconcile: appointment {appt.id} has no manager to escalate to; skipping."
            )
            continue

        lead_name = appt.lead.name if appt.lead else f"Lead #{appt.lead_id}"
        rep_name = rep.name if rep else f"Rep #{appt.user_id}"
        date_str = appt.start_time.strftime("%d %b %Y, %I:%M %p")

        await create_notification(
            db,
            user_id=rep.manager_id,
            title=appt.title,
            notification_type="appointment_escalation",
            message=(
                f"{rep_name}'s appointment with {lead_name} on {date_str} "
                f"has been pending for over a week."
            ),
            link_type="appointment",
            link_id=appt.id,
        )

    if to_escalate:
        logger.info(f"Reconcile: {len(to_escalate)} appointment(s) escalated to manager.")

    # Single commit for all changes
    await db.commit()
