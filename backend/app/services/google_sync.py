"""
Google Workspace Sync — Calendar events and Tasks.

All functions in this module are designed to run as FastAPI BackgroundTasks.
They create their own short-lived DB sessions to update sync metadata
(google_event_id, google_task_id, last_synced_at) after a successful push.

If Google credentials are not configured, these functions log a warning
and return silently — the core CRM functionality is never blocked.
"""

import logging
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.core.config import settings
from app.core.security import decrypt_token
from app.db.session import async_session_factory
from app.db.base import Appointment, Task

logger = logging.getLogger(__name__)


def _get_google_credentials(user) -> Credentials | None:
    """Build Google OAuth credentials from the user's encrypted tokens.

    Returns None if the user has no refresh token or decryption fails.
    """
    if not user.google_refresh_token:
        logger.warning("User %s has no Google refresh token — skipping sync", user.id)
        return None

    try:
        return Credentials(
            token=decrypt_token(user.google_access_token) if user.google_access_token else None,
            refresh_token=decrypt_token(user.google_refresh_token),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
        )
    except Exception:
        logger.exception("Failed to build Google credentials for user %s", user.id)
        return None


# ═══════════════════════════════════════════════════════════════════════
# Google Calendar Sync
# ═══════════════════════════════════════════════════════════════════════


async def sync_appointment_to_calendar(user, appointment, action: str) -> None:
    """Push an appointment to Google Calendar (create or update).

    Args:
        user: The User ORM object (with encrypted Google tokens).
        appointment: The Appointment ORM object.
        action: "create" or "update".
    """
    creds = _get_google_credentials(user)
    if not creds:
        return

    try:
        service = build("calendar", "v3", credentials=creds)

        event_body = {
            "summary": appointment.title,
            "description": appointment.note or "",
            "start": {"dateTime": appointment.start_time.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": appointment.end_time.isoformat(), "timeZone": "UTC"},
        }

        if appointment.location:
            event_body["location"] = appointment.location

        if action == "create":
            event = service.events().insert(calendarId="primary", body=event_body).execute()
            google_event_id = event.get("id")
        elif action == "update" and appointment.google_event_id:
            service.events().update(
                calendarId="primary",
                eventId=appointment.google_event_id,
                body=event_body,
            ).execute()
            google_event_id = appointment.google_event_id
        else:
            logger.warning("Unknown action '%s' or missing google_event_id", action)
            return

        async with async_session_factory() as session:
            from sqlalchemy import update
            await session.execute(
                update(Appointment)
                .where(Appointment.id == appointment.id)
                .values(
                    google_event_id=google_event_id,
                    last_synced_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

        logger.info("Calendar sync OK: appointment %s (%s)", appointment.id, action)

    except Exception:
        logger.exception("Google Calendar sync failed for appointment %s", appointment.id)


async def delete_calendar_event(user, google_event_id: str) -> None:
    """Delete an event from Google Calendar."""
    creds = _get_google_credentials(user)
    if not creds:
        return

    try:
        service = build("calendar", "v3", credentials=creds)
        service.events().delete(calendarId="primary", eventId=google_event_id).execute()
        logger.info("Calendar event deleted: %s", google_event_id)
    except Exception:
        logger.exception("Failed to delete calendar event %s", google_event_id)


# ═══════════════════════════════════════════════════════════════════════
# Google Tasks Sync
# ═══════════════════════════════════════════════════════════════════════


async def sync_task_to_google(user, task, action: str) -> None:
    """Push a task to Google Tasks (create or update).

    Args:
        user: The User ORM object.
        task: The Task ORM object.
        action: "create" or "update".
    """
    creds = _get_google_credentials(user)
    if not creds:
        return

    try:
        service = build("tasks", "v1", credentials=creds)

        task_body = {
            "title": task.title,
            "notes": task.notes or "",
            "status": task.status,
        }

        if task.due:
            task_body["due"] = datetime.combine(task.due, datetime.min.time()).isoformat() + "Z"

        if action == "create":
            result = service.tasks().insert(tasklist="@default", body=task_body).execute()
            google_task_id = result.get("id")
        elif action == "update" and task.google_task_id:
            service.tasks().update(
                tasklist="@default",
                task=task.google_task_id,
                body=task_body,
            ).execute()
            google_task_id = task.google_task_id
        else:
            logger.warning("Unknown action '%s' or missing google_task_id", action)
            return

        async with async_session_factory() as session:
            from sqlalchemy import update
            await session.execute(
                update(Task)
                .where(Task.id == task.id)
                .values(
                    google_task_id=google_task_id,
                    last_synced_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

        logger.info("Google Tasks sync OK: task %s (%s)", task.id, action)

    except Exception:
        logger.exception("Google Tasks sync failed for task %s", task.id)


async def delete_google_task(user, google_task_id: str) -> None:
    """Delete a task from Google Tasks."""
    creds = _get_google_credentials(user)
    if not creds:
        return

    try:
        service = build("tasks", "v1", credentials=creds)
        service.tasks().delete(tasklist="@default", task=google_task_id).execute()
        logger.info("Google task deleted: %s", google_task_id)
    except Exception:
        logger.exception("Failed to delete Google task %s", google_task_id)
