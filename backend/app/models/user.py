"""
User Model — authentication, roles, and Google Workspace tokens.

Columns:
    id, name, email (unique), hashed_password, role,
    google_access_token, google_refresh_token, google_token_expiry

Relationships:
    leads          → Lead  (assigned leads)
    timeline_entries → LeadTimeline
    appointments   → Appointment
    tasks_owned    → Task  (tasks assigned TO this user)
    tasks_assigned → Task  (tasks assigned BY this user)
"""

from datetime import datetime, timezone

from sqlalchemy import Integer, String, Enum, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import UserRole
from sqlalchemy import ForeignKey


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", create_constraint=True),
        nullable=False,
        default=UserRole.sales_rep,
    )

    google_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    manager_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # ── Relationships ─────────────────────────────────────────────────
    manager: Mapped["User"] = relationship("User", remote_side=[id], back_populates="subordinates") # noqa: F821
    subordinates: Mapped[list["User"]] = relationship("User", back_populates="manager") # noqa: F821
    # back_populates creates a bidirectional link between models.
    leads: Mapped[list["Lead"]] = relationship(                        # noqa: F821
        "Lead", back_populates="assigned_rep", lazy="selectin",
    )
    timeline_entries: Mapped[list["LeadTimeline"]] = relationship(     # noqa: F821
        "LeadTimeline", back_populates="user", lazy="selectin",
    )
    appointments: Mapped[list["Appointment"]] = relationship(          # noqa: F821
        "Appointment", back_populates="user", lazy="selectin",
    )
    tasks_owned: Mapped[list["Task"]] = relationship(                  # noqa: F821
        "Task", back_populates="user",
        foreign_keys="[Task.user_id]", lazy="selectin",
    )
    tasks_assigned: Mapped[list["Task"]] = relationship(               # noqa: F821
        "Task", back_populates="assigner",
        foreign_keys="[Task.assigned_by]", lazy="selectin",
    )
    notifications: Mapped[list["Notification"]] = relationship(        # noqa: F821
        "Notification", back_populates="user",
        foreign_keys="[Notification.user_id]", lazy="noload",
    )

    # ── Role helper properties ────────────────────────────────────────
    @property
    def is_sales_rep(self) -> bool:
        return self.role == UserRole.sales_rep

    @property
    def is_manager_or_above(self) -> bool:
        return self.role in (UserRole.manager, UserRole.admin)

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.admin

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role.value}>"
