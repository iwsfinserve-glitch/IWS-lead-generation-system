"""
Due-Date Change Request routes — create, list, approve/reject.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.base import User, Task
from app.models.interaction import TaskDueDateRequest
from app.schemas.due_date_request import (
    DueDateRequestCreate,
    DueDateRequestRead,
    DueDateRequestUpdate,
)
from app.api.dependencies import get_current_user
from app.services.notification_service import create_notification

router = APIRouter(prefix="/due-date-requests", tags=["Due Date Requests"])


@router.post("/", response_model=DueDateRequestRead, status_code=status.HTTP_201_CREATED)
async def create_due_date_request(
    payload: DueDateRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a due-date change request for a manager-assigned task."""
    # Fetch the task
    result = await db.execute(select(Task).where(Task.id == payload.task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Only the assigned rep can request a change
    if task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only request changes for tasks assigned to you")

    # Must be a manager-assigned task
    if task.assigned_by is None or task.assigned_by == current_user.id:
        raise HTTPException(
            status_code=400,
            detail="You can freely modify the due date on self-assigned tasks",
        )

    # Check for existing pending request on this task
    existing = await db.execute(
        select(TaskDueDateRequest).where(
            TaskDueDateRequest.task_id == payload.task_id,
            TaskDueDateRequest.status == "pending",
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="A pending due-date request already exists for this task",
        )

    req = TaskDueDateRequest(
        task_id=payload.task_id,
        requested_by_id=current_user.id,
        manager_id=task.assigned_by,
        requested_date=payload.requested_date,
        requested_end_time=payload.requested_end_time,
        reason=payload.reason,
    )
    db.add(req)

    notif = await create_notification(
        db,
        user_id=task.assigned_by,
        title=task.title,
        notification_type="Tasks",
        message=f"{current_user.name} requested a due-date change for \"{task.title}\" to {payload.requested_date.isoformat()}. Reason: {payload.reason}",
        link_type="task",
        link_id=None,
    )

    await db.commit()
    await db.refresh(req)

    # Update notification link_id now that we have the request ID
    notif.link_id = req.id
    await db.commit()

    return DueDateRequestRead.from_orm_request(req)


@router.get("/", response_model=list[DueDateRequestRead])
async def list_due_date_requests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List due-date change requests.

    - Managers/admins see requests where they are the manager.
    - Sales reps see their own submitted requests.
    """
    query = select(TaskDueDateRequest)

    if current_user.role.value == "sales_rep":
        query = query.where(TaskDueDateRequest.requested_by_id == current_user.id)
    else:
        query = query.where(TaskDueDateRequest.manager_id == current_user.id)

    query = query.order_by(TaskDueDateRequest.created_at.desc())
    result = await db.execute(query)
    return [DueDateRequestRead.from_orm_request(r) for r in result.scalars().all()]


@router.patch("/{request_id}", response_model=DueDateRequestRead)
async def update_due_date_request(
    request_id: int,
    payload: DueDateRequestUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve or reject a due-date change request. Manager/admin only."""
    result = await db.execute(
        select(TaskDueDateRequest).where(TaskDueDateRequest.id == request_id)
    )
    req = result.scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    # Only the assigned manager (or admin) can resolve
    if current_user.role.value not in ("admin",) and req.manager_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the assigning manager can resolve this request")

    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request already {req.status}")

    req.status = payload.status
    req.resolved_at = datetime.now(timezone.utc)

    # If approved, update the actual task due date and end time
    if payload.status == "approved":
        task_result = await db.execute(select(Task).where(Task.id == req.task_id))
        task = task_result.scalar_one_or_none()
        if task:
            task.due = req.requested_date
            if req.requested_end_time is not None:
                task.end_time = req.requested_end_time
                task.end_time_notified = False

    action_word = "approved" if payload.status == "approved" else "rejected"
    task_title = req.task.title if req.task else f"Task #{req.task_id}"
    await create_notification(
        db,
        user_id=req.requested_by_id,
        title=task_title,
        notification_type="Tasks",
        message=f"Your due-date change request for \"{task_title}\" has been {action_word} by {current_user.name}.",
        link_type="task",
        link_id=req.task_id,
    )

    await db.commit()
    await db.refresh(req)

    return DueDateRequestRead.from_orm_request(req)
