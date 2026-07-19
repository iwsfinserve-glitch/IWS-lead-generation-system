"""
SQLAlchemy Declarative Base — the root of all ORM models.

Every model class inherits from `Base` defined here. Alembic's `env.py`
imports `Base.metadata` to auto-detect table schemas for migrations.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Abstract base class for all SQLAlchemy models.

    SQLAlchemy 2.0 style: subclass DeclarativeBase instead of using
    the legacy `declarative_base()` factory function.
    """
    pass


# ═══════════════════════════════════════════════════════════════════════
# Import all models here so that Base.metadata is fully populated
# when Alembic reads it. Without these imports, Alembic's autogenerate
# won't see any tables.
# ═══════════════════════════════════════════════════════════════════════
from app.models.user import User                       # noqa: E402, F401
from app.models.lead import LeadSource, Lead            # noqa: E402, F401
from app.models.interaction import LeadTimeline, Appointment, Task  # noqa: E402, F401
from app.models.interaction import TaskDueDateRequest, Notification  # noqa: E402, F401
from app.models.interaction import LeadTransferRequest               # noqa: E402, F401
from app.models.ai_insight import LeadAIInsight                      # noqa: E402, F401
