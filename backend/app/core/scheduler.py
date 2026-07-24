"""
scheduler.py — APScheduler configuration for background jobs.

Registers:
  - Monthly investor rollover  (cron, 1st of month 00:05)
  - Hourly appointment status reconcile (interval, configurable via
    settings.APPOINTMENT_RECONCILE_INTERVAL_HOURS, default 1 h)
    Also fires once immediately on startup to cover any thresholds
    crossed while the server was offline.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.db.session import async_session_factory
from app.services.rollover import run_monthly_rollover
from app.services.appointment_status import reconcile_appointment_statuses
from app.services.task_status import reconcile_task_statuses

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _rollover_job() -> None:
    """Wrapper invoked by the scheduler — creates its own DB session."""
    logger.info("Scheduler: starting monthly rollover job...")
    async with async_session_factory() as db:
        try:
            count = await run_monthly_rollover(db)
            logger.info(f"Scheduler: monthly rollover completed — {count} leads rolled over.")
        except Exception:
            logger.exception("Scheduler: monthly rollover job failed!")


async def _reconcile_appointments_job() -> None:
    """Wrapper invoked by the scheduler — creates its own DB session."""
    logger.info("Scheduler: running appointment status reconcile...")
    async with async_session_factory() as db:
        try:
            await reconcile_appointment_statuses(db)
            logger.info("Scheduler: appointment reconcile completed.")
        except Exception:
            logger.exception("Scheduler: appointment reconcile job failed!")


async def _reconcile_tasks_job() -> None:
    """Wrapper invoked by the scheduler — creates its own DB session."""
    logger.info("Scheduler: running task status reconcile...")
    async with async_session_factory() as db:
        try:
            await reconcile_task_statuses(db)
            logger.info("Scheduler: task reconcile completed.")
        except Exception:
            logger.exception("Scheduler: task reconcile job failed!")


def setup_scheduler() -> None:
    """Register all background jobs with the scheduler.

    Called once during FastAPI lifespan startup.
    """
    from app.core.config import settings

    scheduler.add_job(
        _rollover_job,
        CronTrigger(day=1, hour=0, minute=5),  # 1st of every month, 00:05 AM
        id="monthly_rollover",
        replace_existing=True,
    )
    logger.info("Scheduler: registered monthly_rollover job (1st of month, 00:05).")

    # Read interval from env (APPOINTMENT_RECONCILE_INTERVAL_HOURS); default 1 h
    interval_hours = getattr(settings, "APPOINTMENT_RECONCILE_INTERVAL_HOURS", 1)
    scheduler.add_job(
        _reconcile_appointments_job,
        IntervalTrigger(hours=int(interval_hours)),
        id="appointment_reconcile",
        replace_existing=True,
        # next_run_time=None causes APScheduler to start on the next full interval;
        # we trigger once immediately on startup via the lifespan hook in main.py
    )
    logger.info(
        f"Scheduler: registered appointment_reconcile job "
        f"(every {interval_hours}h, runs immediately on startup)."
    )

    scheduler.add_job(
        _reconcile_tasks_job,
        IntervalTrigger(minutes=15),
        id="task_reconcile",
        replace_existing=True,
    )
    logger.info("Scheduler: registered task_reconcile job (every 15m).")
