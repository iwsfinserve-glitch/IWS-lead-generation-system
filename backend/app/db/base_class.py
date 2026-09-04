"""
SQLAlchemy Declarative Base class.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Abstract base class for all SQLAlchemy models."""
    pass
