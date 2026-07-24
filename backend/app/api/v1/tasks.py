"""
Task routes — CRUD with background Google Tasks sync.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.base import User, Task
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate, TaskSelfCreate
from app.api.dependencies import get_current_user, require_roles
from app.services.google_sync import sync_task_to_google, delete_google_task

router = APIRouter(prefix="/tasks", tags=["Tasks"])


async def _create_task_record(
    *,
    user_id: int,
    assigned_by: int,
    title: str,
    notes: str | None,
    due: datetime | None,
    end_time: datetime | None,
    background_tasks: BackgroundTasks,
    db: AsyncSession,
    current_user: User,
) -> TaskRead:
    """Shared helper that creates a Task record and optionally syncs to Google."""
    task = Task(
        user_id=user_id,
        assigned_by=assigned_by,
        title=title,
        notes=notes,
        due=due,
        end_time=end_time,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    if current_user.google_refresh_token:
        background_tasks.add_task(sync_task_to_google, current_user, task, "create")

    return TaskRead.from_orm_task(task)


@router.get("/", response_model=list[TaskRead])
async def list_tasks(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    user_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List tasks. Sales reps see only tasks assigned to them."""
    query = select(Task)
    if current_user.is_sales_rep:
        query = query.where(Task.user_id == current_user.id)
    elif user_id is not None:
        query = query.where(Task.user_id == user_id)
    query = query.order_by(Task.assigned_on.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return [TaskRead.from_orm_task(t) for t in result.scalars().all()]


@router.post("/", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a task and assign it to a user."""
    if current_user.is_sales_rep and payload.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Sales reps can only create tasks for themselves")

    target = await db.execute(select(User).where(User.id == payload.user_id))
    target_user = target.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="Assigned user not found")

    if current_user.is_manager_or_above and not current_user.is_admin:
        if payload.user_id != current_user.id and target_user.manager_id != current_user.id:
            raise HTTPException(status_code=403, detail="Managers can only assign tasks to their direct reports")

    return await _create_task_record(
        user_id=payload.user_id,
        assigned_by=current_user.id,
        title=payload.title,
        notes=payload.notes,
        due=payload.due,
        end_time=payload.end_time,
        background_tasks=background_tasks,
        db=db,
        current_user=current_user,
    )


@router.post("/self", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_self_task(
    payload: TaskSelfCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a task assigned to the current user (self-assignment)."""
    return await _create_task_record(
        user_id=current_user.id,
        assigned_by=current_user.id,
        title=payload.title,
        notes=payload.notes,
        due=payload.due,
        end_time=payload.end_time,
        background_tasks=background_tasks,
        db=db,
        current_user=current_user,
    )


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a task. Sets completed_at when status changes to 'completed'."""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if current_user.is_sales_rep and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own tasks")

    # Reps cannot change due date or end time on tasks assigned by someone else
    if (current_user.is_sales_rep
            and ("due" in payload.model_dump(exclude_unset=True) or "end_time" in payload.model_dump(exclude_unset=True))
            and task.assigned_by is not None
            and task.assigned_by != current_user.id):
        raise HTTPException(
            status_code=403,
            detail="You cannot change the due date or end time on a manager-assigned task. "
                   "Please submit a due date change request instead.",
        )

    update_data = payload.model_dump(exclude_unset=True)
    old_status = task.status

    for field, value in update_data.items():
        setattr(task, field, value)

    if "status" in update_data and update_data["status"] == "completed" and old_status != "completed":
        task.completed_at = datetime.now(timezone.utc)
    elif "status" in update_data and update_data["status"] == "needsAction":
        task.completed_at = None

    await db.commit()
    await db.refresh(task)

    if current_user.google_refresh_token and task.google_task_id:
        background_tasks.add_task(sync_task_to_google, current_user, task, "update")

    return TaskRead.from_orm_task(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a task and remove from Google Tasks."""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if current_user.is_sales_rep and task.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own tasks")

    google_task_id = task.google_task_id
    await db.delete(task)
    await db.commit()

    if current_user.google_refresh_token and google_task_id:
        background_tasks.add_task(delete_google_task, current_user, google_task_id)

