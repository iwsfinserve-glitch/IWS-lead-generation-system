"""
Shared enums used across models and schemas.

Defined separately to avoid circular imports between
schemas (which need the enum for validation) and models
(which need it for column definitions).
"""

import enum


class UserRole(str, enum.Enum):
    """User roles for RBAC."""
    admin = "admin"
    manager = "manager"
    sales_rep = "sales_rep"


class LeadStatus(str, enum.Enum):
    """Pipeline stages for a lead."""
    unassigned = "unassigned"
    in_progress = "in_progress"
    potential = "potential"
    non_potential = "non_potential"
    converted_to_investor = "converted_to_investor"
    existing_investor = "existing_investor"


class AppointmentMode(str, enum.Enum):
    """Appointment meeting mode."""
    online = "online"
    in_person = "in_person"


class DueDateRequestStatus(str, enum.Enum):
    """Status for task due-date change requests."""
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
