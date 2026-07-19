"""
Google Workspace Sync - Calendar events and Tasks.

All functions in this module are designed to run as FastAPI BackgroundTasks.
They create their own short-lived DB sessions to update sync metadata
(google_event_id, google_task_id, last_synced_at) after a successful push.

If Google credentials are not configured, these functions log a warning
and return silently - the core CRM functionality is never blocked.
"""

import logging
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import settings
from app.core.security import decrypt_token, encrypt_token
from app.db.session import async_session_factory
from app.db.base import Appointment, Task

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_google_credentials(user) -> Credentials | None:
    """Build Google OAuth credentials from the user's encrypted tokens.

    Handles automatic token refresh if the access token has expired.
    Returns None if the user has no refresh token or decryption fails.
    """
    if not user.google_refresh_token:
        logger.warning("User %s has no Google refresh token - skipping sync", user.id)
        return None

    try:
        access_token = decrypt_token(user.google_access_token) if user.google_access_token else None
        refresh_token = decrypt_token(user.google_refresh_token)

        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
        )

        # Proactively refresh the access token if it is expired.
        if not creds.valid or creds.expired:
            creds.refresh(Request())
            # Persist the freshly-issued access token back to the DB so we
            # don't have to exchange the refresh token on every single call.
            _schedule_token_persist(user.id, creds.token)

        return creds
    except Exception:
        logger.exception("Failed to build Google credentials for user %s", user.id)
        return None


def _schedule_token_persist(user_id: int, new_access_token: str) -> None:
    """Fire-and-forget: persist a refreshed access token back to the DB.

    We do this inside a synchronous helper that schedules a coroutine via
    asyncio rather than blocking. Called only from _get_google_credentials.
    """
    import asyncio

    async def _persist():
        try:
            from sqlalchemy import update
            from app.db.base import User
            async with async_session_factory() as session:
                await session.execute(
                    update(User)
                    .where(User.id == user_id)
                    .values(
                        google_access_token=encrypt_token(new_access_token),
                        google_token_expiry=datetime.now(timezone.utc),
                    )
                )
                await session.commit()
        except Exception:
            logger.exception("Failed to persist refreshed access token for user %s", user_id)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_persist())
        else:
            loop.run_until_complete(_persist())
    except RuntimeError:
        # No event loop available - skip (token will just be refreshed next time)
        pass


def _build_calendar_event_body(appointment) -> dict:
    """Construct the Google Calendar event payload from an Appointment ORM object."""
    body = {
        "summary": appointment.title,
        "description": appointment.note or "",
        "start": {
            "dateTime": appointment.start_time.isoformat(),
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": appointment.end_time.isoformat(),
            "timeZone": "UTC",
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 60},
                {"method": "popup", "minutes": 15},
            ],
        },
        "source": {
            "title": "IWS Lead Management CRM",
            "url": "http://localhost:8501",
        },
    }
    if appointment.location:
        body["location"] = appointment.location

    return body


# ===========================================================================
# Google Calendar Sync
# ===========================================================================


async def sync_appointment_to_calendar(user, appointment, action: str) -> None:
    """Push a single appointment to Google Calendar (create or update).

    Args:
        user:        The User ORM object (with encrypted Google tokens).
        appointment: The Appointment ORM object.
        action:      "create" or "update".
    """
    creds = _get_google_credentials(user)
    if not creds:
        return

    try:
        service = build("calendar", "v3", credentials=creds)
        event_body = _build_calendar_event_body(appointment)

        if action == "create":
            event = (
                service.events()
                .insert(calendarId="primary", body=event_body)
                .execute()
            )
            google_event_id = event.get("id")
        elif action == "update" and appointment.google_event_id:
            service.events().update(
                calendarId="primary",
                eventId=appointment.google_event_id,
                body=event_body,
            ).execute()
            google_event_id = appointment.google_event_id
        else:
            logger.warning(
                "Unknown action '%s' or missing google_event_id for appointment %s",
                action,
                appointment.id,
            )
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

    except HttpError as e:
        logger.error(
            "Google Calendar API error for appointment %s: %s %s",
            appointment.id, e.status_code, e.reason,
        )
    except Exception:
        logger.exception("Google Calendar sync failed for appointment %s", appointment.id)


async def delete_calendar_event(user, google_event_id: str) -> None:
    """Delete an event from Google Calendar by its event ID."""
    creds = _get_google_credentials(user)
    if not creds:
        return

    try:
        service = build("calendar", "v3", credentials=creds)
        service.events().delete(calendarId="primary", eventId=google_event_id).execute()
        logger.info("Calendar event deleted: %s", google_event_id)
    except HttpError as e:
        if e.status_code == 404:
            logger.info("Calendar event %s already deleted or not found", google_event_id)
        else:
            logger.error("Google Calendar API error deleting %s: %s", google_event_id, e.reason)
    except Exception:
        logger.exception("Failed to delete calendar event %s", google_event_id)


async def bulk_sync_all_appointments(user_id: int) -> dict:
    """Sync ALL existing appointments for a user to Google Calendar.

    Called once after a user first connects their Google account to backfill
    their calendar with all appointments already in the CRM.

    Returns a summary dict with counts of synced and failed appointments.

    Args:
        user_id: The ID of the user whose appointments should be synced.
    """
    synced = 0
    failed = 0
    skipped = 0

    async with async_session_factory() as session:
        from sqlalchemy import select
        from app.db.base import User

        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        if not user or not user.google_refresh_token:
            logger.warning("bulk_sync: user %s not found or not Google-connected", user_id)
            return {"synced": 0, "failed": 0, "skipped": 0}

        creds = _get_google_credentials(user)
        if not creds:
            return {"synced": 0, "failed": 0, "skipped": 0}

        appt_result = await session.execute(
            select(Appointment)
            .where(Appointment.user_id == user_id)
            .order_by(Appointment.start_time.asc())
        )
        appointments = appt_result.scalars().all()

        if not appointments:
            logger.info("bulk_sync: no appointments found for user %s", user_id)
            return {"synced": 0, "failed": 0, "skipped": 0}

        logger.info(
            "bulk_sync: starting calendar sync for user %s (%d appointments)",
            user_id, len(appointments),
        )

        service = build("calendar", "v3", credentials=creds)
        from sqlalchemy import update

        for appt in appointments:
            # If already synced, update it; otherwise insert a new event.
            action = "update" if appt.google_event_id else "create"
            try:
                event_body = _build_calendar_event_body(appt)

                if action == "create":
                    event = (
                        service.events()
                        .insert(calendarId="primary", body=event_body)
                        .execute()
                    )
                    google_event_id = event.get("id")
                else:
                    try:
                        service.events().update(
                            calendarId="primary",
                            eventId=appt.google_event_id,
                            body=event_body,
                        ).execute()
                        google_event_id = appt.google_event_id
                    except HttpError as e:
                        if e.status_code == 404:
                            # Event was deleted from Google Calendar; re-create it.
                            event = (
                                service.events()
                                .insert(calendarId="primary", body=event_body)
                                .execute()
                            )
                            google_event_id = event.get("id")
                        else:
                            raise

                await session.execute(
                    update(Appointment)
                    .where(Appointment.id == appt.id)
                    .values(
                        google_event_id=google_event_id,
                        last_synced_at=datetime.now(timezone.utc),
                    )
                )
                synced += 1

            except HttpError as e:
                logger.error(
                    "bulk_sync: Google API error for appointment %s: %s %s",
                    appt.id, e.status_code, e.reason,
                )
                failed += 1
            except Exception:
                logger.exception("bulk_sync: unexpected error for appointment %s", appt.id)
                failed += 1

        await session.commit()

    logger.info(
        "bulk_sync complete for user %s: synced=%d, failed=%d, skipped=%d",
        user_id, synced, failed, skipped,
    )
    return {"synced": synced, "failed": failed, "skipped": skipped}


# ===========================================================================
# Google Tasks Sync
# ===========================================================================


async def sync_task_to_google(user, task, action: str) -> None:
    """Push a task to Google Tasks (create or update).

    Args:
        user:   The User ORM object.
        task:   The Task ORM object.
        action: "create" or "update".
    """
    creds = _get_google_credentials(user)
    if not creds:
        return

    try:
        service = build("tasks", "v1", credentials=creds)

        task_body: dict = {
            "title": task.title,
            "notes": task.notes or "",
            "status": task.status,
        }

        if task.due:
            task_body["due"] = (
                datetime.combine(task.due, datetime.min.time()).isoformat() + "Z"
            )

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
            logger.warning("Unknown action '%s' or missing google_task_id for task %s", action, task.id)
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

    except HttpError as e:
        logger.error("Google Tasks API error for task %s: %s %s", task.id, e.status_code, e.reason)
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
    except HttpError as e:
        if e.status_code == 404:
            logger.info("Google task %s already deleted or not found", google_task_id)
        else:
            logger.error("Google Tasks API error deleting %s: %s", google_task_id, e.reason)
    except Exception:
        logger.exception("Failed to delete Google task %s", google_task_id)
