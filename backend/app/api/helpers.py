"""
Shared API helpers and database retrieval utilities.

Centralizes common entity lookup patterns to prevent code duplication
and circular import dependencies across route modules.
"""

from typing import Sequence
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.base import ExecutableOption

from app.models.lead import Lead


async def get_lead_or_404(
    lead_id: int,
    db: AsyncSession,
    options: Sequence[ExecutableOption] | None = None,
) -> Lead:
    """Fetch a Lead ORM record by ID or raise HTTP 404.

    Args:
        lead_id: Primary key of the lead.
        db: Active async database session.
        options: Optional list of SQLAlchemy loader options (e.g. selectinload).

    Returns:
        The matched Lead instance.

    Raises:
        HTTPException(404) if no matching lead is found.
    """
    stmt = select(Lead).where(Lead.id == lead_id)
    if options:
        stmt = stmt.options(*options)

    result = await db.execute(stmt)
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )
    return lead


# Alias for backward-compatible internal naming
_get_lead_or_404 = get_lead_or_404
