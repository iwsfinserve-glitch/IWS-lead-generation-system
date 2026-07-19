"""
Interaction Models — LeadTimeline, Appointment, and Task.

LeadTimeline — The audit engine. Every meaningful action on a lead
               (status change, note, appointment booked, etc.) is logged
               here with a JSONB `event_metadata` column for AI context.

Appointment  — A scheduled meeting tied to a lead, optionally synced
               to Google Calendar.

Task         — An internal work item assigned to a user, optionally
               synced to Google Tasks.
"""

from datetime import date, datetime, timezone

from sqlalchemy import (
    Integer, String, Enum, Date, DateTime, ForeignKey, Text, JSON,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

JSON_VARIANT = JSON().with_variant(JSONB, "postgresql")

from app.db.base import Base
from app.models.enums import AppointmentMode





class LeadTimeline(Base):
    """Immutable audit log for all lead-related events.

    Every status change, note, appointment booking, and other meaningful
    action is recorded here. The `event_metadata` JSONB column stores
    structured data that the AI reporting engine reads for context.

    Example event_metadata:
        {"old_status": "new", "new_status": "in_progress", "note": "First call made"}
        {"appointment_title": "Demo call", "mode": "online"}
    """

    __tablename__ = "lead_timeline"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    lead_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="e.g. status_change, note_added, appointment_booked, task_created",
    )
    event_metadata: Mapped[dict] = mapped_column(
        JSON_VARIANT, nullable=False, default=dict,
        comment="Structured event payload for AI report context",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────
    lead: Mapped["Lead"] = relationship("Lead", back_populates="timeline", lazy="selectin")      # noqa: F821
    user: Mapped["User"] = relationship("User", back_populates="timeline_entries", lazy="selectin")  # noqa: F821

    def __repr__(self) -> str:
        return f"<LeadTimeline id={self.id} lead_id={self.lead_id} type={self.event_type!r}>"


class Appointment(Base):
    """A scheduled meeting/call tied to a lead.

    Optionally synced to Google Calendar. The `google_event_id` column
    stores the Google Calendar event ID for update/delete operations.
    """

    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    lead_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False,
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    mode: Mapped[AppointmentMode] = mapped_column(
        Enum(AppointmentMode, name="appointment_mode", create_constraint=True),
        nullable=False,
        default=AppointmentMode.online,
    )
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    google_event_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True,
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # ── Relationships ──────────────────────────────────────────────────
    lead: Mapped["Lead"] = relationship("Lead", back_populates="appointments", lazy="selectin")    # noqa: F821
    user: Mapped["User"] = relationship("User", back_populates="appointments", lazy="selectin")    # noqa: F821

    def __repr__(self) -> str:
        return f"<Appointment id={self.id} title={self.title!r}>"





class Task(Base):
    """An internal work item assigned to a user.

    Tasks can be assigned by a manager/admin (assigned_by) to a
    sales_rep (user_id). Optionally synced to Google Tasks.
    """

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False,
    )
    assigned_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True,
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="needsAction",
        comment="needsAction | completed",
    )

    assigned_on: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    due: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    google_task_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True,
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # ── Relationships ──────────────────────────────────────────────────
    user: Mapped["User"] = relationship(                               # noqa: F821
        "User", back_populates="tasks_owned",
        foreign_keys=[user_id], lazy="selectin",
    )
    assigner: Mapped["User | None"] = relationship(                    # noqa: F821
        "User", back_populates="tasks_assigned",
        foreign_keys=[assigned_by], lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Task id={self.id} title={self.title!r} status={self.status}>"


class TaskDueDateRequest(Base):
    """A request from a sales rep to change a task's due date.

    When a manager assigns a task, the rep cannot freely change the due
    date. Instead they submit a request here, which the manager can
    approve or reject. On approval the Task.due column is updated
    automatically.
    """

    __tablename__ = "task_due_date_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    requested_by_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False,
    )
    manager_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False,
    )

    requested_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending",
        comment="pending | approved | rejected",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # ── Relationships ──────────────────────────────────────────────────
    task: Mapped["Task"] = relationship("Task", lazy="selectin")
    requester: Mapped["User"] = relationship(                          # noqa: F821
        "User", foreign_keys=[requested_by_id], lazy="selectin",
    )
    manager: Mapped["User"] = relationship(                            # noqa: F821
        "User", foreign_keys=[manager_id], lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<TaskDueDateRequest id={self.id} task_id={self.task_id} status={self.status}>"


class Notification(Base):
    """Global notification for a user.

    Created automatically when events occur (e.g. due-date request
    approved/rejected). The frontend shows a bell icon with an unread
    count badge.
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    message: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notification_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_read: Mapped[bool] = mapped_column(default=False, nullable=False)

    link_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="Optional entity type for deep-linking, e.g. 'task', 'request'",
    )
    link_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Optional entity ID for deep-linking",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="notifications", lazy="selectin")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Notification id={self.id} user_id={self.user_id} read={self.is_read}>"


class LeadTransferRequest(Base):
    """A request to transfer a lead from one sales rep to another.

    Sales reps submit a transfer request, which managers/admins can
    approve or reject. On approval, Lead.assigned_rep_id is updated
    automatically.
    """

    __tablename__ = "lead_transfer_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    lead_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    from_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False,
    )
    to_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False,
    )

    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending",
        comment="pending | approved | rejected",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────
    lead: Mapped["Lead"] = relationship("Lead", lazy="selectin")                       # noqa: F821
    from_user: Mapped["User"] = relationship(                                          # noqa: F821
        "User", foreign_keys=[from_user_id], lazy="selectin",
    )
    to_user: Mapped["User"] = relationship(                                            # noqa: F821
        "User", foreign_keys=[to_user_id], lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<LeadTransferRequest id={self.id} lead_id={self.lead_id} status={self.status}>"
