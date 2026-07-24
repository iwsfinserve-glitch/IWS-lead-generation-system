import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interaction import Task, Notification

logger = logging.getLogger(__name__)

async def reconcile_task_statuses(db: AsyncSession) -> None:
    """
    Check for overdue tasks that haven't been notified yet.
    Create a notification for the assigned user and mark as notified.
    """
    now = datetime.now(timezone.utc)
    
    # Find all tasks that are needsAction, have an end_time in the past, and haven't been notified
    query = (
        select(Task)
        .where(
            Task.status == "needsAction",
            Task.end_time != None,
            Task.end_time <= now,
            Task.end_time_notified == False
        )
    )
    result = await db.execute(query)
    overdue_tasks = result.scalars().all()

    if not overdue_tasks:
        return

    for task in overdue_tasks:
        # Create a notification for the assigned user
        notification = Notification(
            user_id=task.user_id,
            title="Task Overdue",
            message=f"The task '{task.title}' is overdue.",
            notification_type="task_overdue",
            link_type="task",
            link_id=task.id,
        )
        db.add(notification)
        task.end_time_notified = True

    await db.commit()
    logger.info(f"Reconcile: {len(overdue_tasks)} task(s) marked as overdue and users notified.")
