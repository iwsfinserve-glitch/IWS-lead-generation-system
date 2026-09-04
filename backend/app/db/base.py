"""
SQLAlchemy Declarative Base — the root of all ORM models.

Every model class inherits from `Base` defined here.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Abstract base class for all SQLAlchemy models.

    SQLAlchemy 2.0 style: subclass DeclarativeBase instead of using
    the legacy `declarative_base()` factory function.
    """
    pass
