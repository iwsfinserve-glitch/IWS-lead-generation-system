"""
task_status.py — Background reconcile service for task escalation lifecycle.

Escalation tiers (automated):
    Tier 1: task overdue (end_time <= now)
            → notify assigned rep
            → set end_time_notified = True

    Tier 2: still incomplete after 7 days past due
            → notify the assigning manager (or all managers if no assigner)
            → set manager_alerted = True, record manager_alerted_at

    Tier 3: still incomplete 4 days after manager was alerted
            → notify all admins
            → set admin_alerted = True

Manual completion (needsAction → completed) is handled via the
PATCH /tasks/{id} endpoint.
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interaction import Task, Notification
from app.db.base import User
from app.models.enums import UserRole
from app.services.notification_service import create_notification

logger = logging.getLogger(__name__)

_7_DAYS = timedelta(days=7)
_4_DAYS = timedelta(days=4)


async def reconcile_task_statuses(db: AsyncSession) -> None:
    """Batch reconcile task escalation tiers and fire notifications.

    Runs as a scheduled job (every 15 minutes). Each call:
      1. Notifies the rep for newly overdue tasks.
      2. Escalates to manager after 7 days past due.
      3. Escalates to admin 2 days after manager was alerted.

    Commits once at the end after all changes are queued.
    """
    now = datetime.now(timezone.utc)
    seven_days_ago = now - _7_DAYS
    four_days_ago = now - _4_DAYS

    # ── Tier 1: Notify rep when task goes overdue ─────────────────────
    result = await db.execute(
        select(Task).where(
            Task.status == "needsAction",
            Task.end_time != None,      # noqa: E711
            Task.end_time <= now,
            Task.end_time_notified == False,   # noqa: E712
        )
    )
    newly_overdue = result.scalars().all()

    for task in newly_overdue:
        task.end_time_notified = True
        await create_notification(
            db,
            user_id=task.user_id,
            title="Task Overdue",
            message=f"Your task '{task.title}' is overdue. Please complete it as soon as possible.",
            notification_type="task_overdue",
            link_type="task",
            link_id=task.id,
        )

    if newly_overdue:
        logger.info(f"Reconcile: {len(newly_overdue)} task(s) overdue — rep(s) notified (Tier 1).")

    # ── Tier 2: Escalate to manager after 7 days ─────────────────────
    result2 = await db.execute(
        select(Task).where(
            Task.status == "needsAction",
            Task.end_time != None,          # noqa: E711
            Task.end_time <= seven_days_ago,
            Task.manager_alerted == False,  # noqa: E712
        )
    )
    tier2_tasks = result2.scalars().all()

    for task in tier2_tasks:
        task.manager_alerted = True
        task.manager_alerted_at = now

        # Load the assigned rep to get their name
        rep_result = await db.execute(select(User).where(User.id == task.user_id))
        rep = rep_result.scalar_one_or_none()
        rep_name = rep.name if rep else f"Rep #{task.user_id}"

        due_str = task.end_time.strftime("%d %b %Y, %I:%M %p") if task.end_time else "N/A"

        if task.assigned_by:
            # Notify the specific manager who assigned this task
            await create_notification(
                db,
                user_id=task.assigned_by,
                title="Task Overdue — Escalation",
                message=(
                    f"{rep_name}'s task '{task.title}' (due {due_str}) "
                    f"has been incomplete for over a week."
                ),
                notification_type="task_escalation_manager",
                link_type="task",
                link_id=task.id,
            )
        else:
            # No specific assigner — notify all managers and admins
            mgr_result = await db.execute(
                select(User).where(User.role.in_([UserRole.manager, UserRole.admin]))
            )
            managers = mgr_result.scalars().all()
            for mgr in managers:
                await create_notification(
                    db,
                    user_id=mgr.id,
                    title="Task Overdue — Escalation",
                    message=(
                        f"{rep_name}'s task '{task.title}' (due {due_str}) "
                        f"has been incomplete for over a week."
                    ),
                    notification_type="task_escalation_manager",
                    link_type="task",
                    link_id=task.id,
                )

    if tier2_tasks:
        logger.info(f"Reconcile: {len(tier2_tasks)} task(s) escalated to manager (Tier 2).")

    # ── Tier 3: Escalate to admin 4 days after manager was alerted ───
    result3 = await db.execute(
        select(Task).where(
            Task.status == "needsAction",
            Task.manager_alerted == True,           # noqa: E712
            Task.manager_alerted_at != None,        # noqa: E711
            Task.manager_alerted_at <= four_days_ago,
            Task.admin_alerted == False,            # noqa: E712
        )
    )
    tier3_tasks = result3.scalars().all()

    # Fetch all admins once for the batch
    admin_result = await db.execute(
        select(User).where(User.role == UserRole.admin)
    )
    admins = admin_result.scalars().all()

    for task in tier3_tasks:
        task.admin_alerted = True

        rep_result = await db.execute(select(User).where(User.id == task.user_id))
        rep = rep_result.scalar_one_or_none()
        rep_name = rep.name if rep else f"Rep #{task.user_id}"

        due_str = task.end_time.strftime("%d %b %Y, %I:%M %p") if task.end_time else "N/A"

        for admin in admins:
            await create_notification(
                db,
                user_id=admin.id,
                title="Task Unresolved — Admin Escalation",
                message=(
                    f"{rep_name}'s task '{task.title}' (due {due_str}) "
                    f"remains incomplete 4 days after the manager was alerted."
                ),
                notification_type="task_escalation_admin",
                link_type="task",
                link_id=task.id,
            )

    if tier3_tasks:
        logger.info(f"Reconcile: {len(tier3_tasks)} task(s) escalated to admin (Tier 3).")

    # Single commit for all tiers
    await db.commit()
