"""
Notification service — shared helper for creating notifications.

Extracts the duplicated Notification ORM construction into a single
reusable function used by all routers (due_date_requests, lead_transfers, etc.).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interaction import Notification
from app.models.enums import UserRole


async def create_notification(
    db: AsyncSession,
    *,
    user_id: int,
    title: str,
    message: str,
    notification_type: str,
    link_type: str | None = None,
    link_id: int | None = None,
) -> Notification:
    """Create and add a notification to the session (does NOT commit).

    Args:
        db: Active async session.
        user_id: Recipient user ID.
        title: Short title for the notification.
        message: Full notification message body.
        notification_type: Category (e.g. "Tasks", "Leads").
        link_type: Optional entity type for deep-linking (e.g. "task", "lead").
        link_id: Optional entity ID for deep-linking.

    Returns:
        The Notification ORM instance (already added to session).
    """
    notif = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        link_type=link_type,
        link_id=link_id,
    )
    db.add(notif)
    return notif


async def notify_managers(
    db: AsyncSession,
    *,
    title: str,
    message: str,
    notification_type: str,
    link_type: str | None = None,
    link_id: int | None = None,
) -> list[Notification]:
    """Send a notification to all managers and admins.

    Returns:
        List of created Notification instances.
    """
    from app.db.base import User

    result = await db.execute(
        select(User).where(User.role.in_([UserRole.manager, UserRole.admin]))
    )
    managers = result.scalars().all()

    notifications = []
    for mgr in managers:
        notif = await create_notification(
            db,
            user_id=mgr.id,
            title=title,
            message=message,
            notification_type=notification_type,
            link_type=link_type,
            link_id=link_id,
        )
        notifications.append(notif)
    return notifications


async def notify_sales_reps_and_managers(
    db: AsyncSession,
    *,
    title: str,
    message: str,
    notification_type: str,
    link_type: str | None = None,
    link_id: int | None = None,
) -> list[Notification]:
    """Send a notification to all sales reps and managers (not admins).

    Used for high-priority SEO lead arrivals so the right people can
    immediately view and claim the lead.

    Returns:
        List of created Notification instances.
    """
    from app.db.base import User

    result = await db.execute(
        select(User).where(User.role.in_([UserRole.sales_rep, UserRole.manager]))
    )
    recipients = result.scalars().all()

    notifications = []
    for user in recipients:
        notif = await create_notification(
            db,
            user_id=user.id,
            title=title,
            message=message,
            notification_type=notification_type,
            link_type=link_type,
            link_id=link_id,
        )
        notifications.append(notif)
    return notifications
