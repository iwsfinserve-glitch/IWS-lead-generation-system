"""
scheduler.py — APScheduler configuration for background jobs.

Registers the monthly investor rollover cron job and provides
lifecycle hooks (start / shutdown) for FastAPI's lifespan.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.db.session import async_session_factory
from app.services.rollover import run_monthly_rollover

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


def setup_scheduler() -> None:
    """Register all background jobs with the scheduler.

    Called once during FastAPI lifespan startup.
    """
    scheduler.add_job(
        _rollover_job,
        CronTrigger(day=1, hour=0, minute=5),  # 1st of every month, 00:05 AM
        id="monthly_rollover",
        replace_existing=True,
    )
    logger.info("Scheduler: registered monthly_rollover job (1st of month, 00:05).")
