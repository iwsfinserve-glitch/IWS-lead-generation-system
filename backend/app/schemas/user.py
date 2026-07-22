"""
Pydantic schemas for User operations — registration, login, responses, and JWT tokens.
"""

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field

from app.models.enums import UserRole


class UserCreate(BaseModel):
    """Schema for creating a new user (admin-only registration)."""
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    phone_number: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)
    role: UserRole = UserRole.sales_rep
    manager_id: int | None = None


class UserRead(BaseModel):
    """Schema returned when reading user data — excludes sensitive fields."""
    id: int
    name: str
    email: str
    phone_number: str
    role: UserRole
    manager_id: int | None = None
    google_connected: bool = False

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_user(cls, user) -> "UserRead":
        return cls(
            id=user.id,
            name=user.name,
            email=user.email,
            phone_number=user.phone_number,
            role=user.role,
            manager_id=user.manager_id,
            google_connected=user.google_refresh_token is not None,
        )


class UserUpdate(BaseModel):
    """Schema for updating an existing user — all fields optional."""
    name: str | None = Field(None, min_length=1, max_length=255)
    email: EmailStr | None = None
    phone_number: str | None = Field(None, min_length=1, max_length=50)
    password: str | None = Field(None, min_length=6, max_length=128)
    role: UserRole | None = None
    manager_id: int | None = None


class Token(BaseModel):
    """JWT token response returned after successful login."""
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Decoded JWT payload used internally by the auth dependency."""
    user_id: int
    role: UserRole
