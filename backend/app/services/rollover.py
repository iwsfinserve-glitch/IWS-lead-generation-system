"""
rollover.py — Monthly investor rollover service.

Runs on the 1st of every month to bulk-convert all leads with status
'converted_to_investor' to 'existing_investor'. Each transition is
logged to the lead's timeline with the assigned rep's user_id.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Lead, LeadTimeline
from app.models.enums import LeadStatus

logger = logging.getLogger(__name__)


async def run_monthly_rollover(db: AsyncSession) -> int:
    """Bulk-convert all 'converted_to_investor' leads to 'existing_investor'.

    Uses a two-step approach:
      1. SELECT leads to roll over (needed for timeline entries).
      2. Bulk UPDATE status in a single SQL statement.
      3. Batch INSERT timeline entries for all affected leads.

    Returns:
        The number of leads that were rolled over.
    """
    # Step 1: Fetch IDs and rep assignments for timeline entries
    result = await db.execute(
        select(Lead.id, Lead.assigned_rep_id)
        .where(Lead.status == LeadStatus.converted_to_investor)
    )
    rows = result.all()

    if not rows:
        logger.info("Monthly rollover: no converted leads to roll over.")
        return 0

    lead_ids = [r.id for r in rows]

    # Step 2: Bulk UPDATE all matching leads in a single SQL statement
    await db.execute(
        update(Lead)
        .where(Lead.id.in_(lead_ids))
        .values(status=LeadStatus.existing_investor)
    )

    # Step 3: Batch INSERT timeline entries for leads with an assigned rep
    timeline_entries = [
        LeadTimeline(
            lead_id=r.id,
            user_id=r.assigned_rep_id,
            event_type="status_change",
            event_metadata={
                "old_status": LeadStatus.converted_to_investor.value,
                "new_status": LeadStatus.existing_investor.value,
                "changed_by": "monthly_rollover_job",
            },
        )
        for r in rows
        if r.assigned_rep_id is not None
    ]
    if timeline_entries:
        db.add_all(timeline_entries)

    await db.commit()
    count = len(lead_ids)
    logger.info(f"Monthly rollover: rolled over {count} leads to existing_investor.")
    return count
