"""
Lead Source routes — CRUD for acquisition channels.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.base import User, LeadSource
from app.schemas.lead import LeadSourceCreate, LeadSourceRead, LeadSourceUpdate
from app.api.dependencies import get_current_user, require_roles

router = APIRouter(prefix="/sources", tags=["Lead Sources"])


@router.get("/", response_model=list[LeadSourceRead])
async def list_sources(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all lead sources."""
    result = await db.execute(select(LeadSource).order_by(LeadSource.id))
    return result.scalars().all()


@router.post("/", response_model=LeadSourceRead, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: LeadSourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
):
    """Create a new lead source. Admin/Manager only."""
    existing = await db.execute(select(LeadSource).where(LeadSource.name == payload.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Source name already exists")

    source = LeadSource(name=payload.name, priority=payload.priority)
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


@router.patch("/{source_id}", response_model=LeadSourceRead)
async def update_source(
    source_id: int,
    payload: LeadSourceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
):
    """Update a lead source. Admin/Manager only."""
    result = await db.execute(select(LeadSource).where(LeadSource.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(source, field, value)

    await db.commit()
    await db.refresh(source)
    return source


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    """Delete a lead source. Admin only."""
    result = await db.execute(select(LeadSource).where(LeadSource.id == source_id))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    await db.delete(source)
    await db.commit()
