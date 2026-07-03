"""
Auth routes — registration, login, user listing, and Google OAuth connection.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from google_auth_oauthlib.flow import Flow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    encrypt_token, decrypt_token,
)
from app.db.session import get_db
from app.db.base import User
from app.models.enums import UserRole
from app.schemas.user import UserCreate, UserRead, UserUpdate, Token
from app.api.dependencies import get_current_user, require_roles
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/auth", tags=["Auth"])

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/tasks",
]


def _build_google_flow() -> Flow:
    """Build a Google OAuth2 Flow from .env credentials."""
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth credentials are not configured in .env",
        )

    return Flow.from_client_config(
        client_config={
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
            }
        },
        scopes=GOOGLE_SCOPES,
    )


# ═══════════════════════════════════════════════════════════════════════
# Standard Auth (JWT)
# ═══════════════════════════════════════════════════════════════════════


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register_user(
    request: Request,
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    """Create a new user. Admin only."""
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        name=payload.name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        manager_id=payload.manager_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserRead.from_orm_user(user)


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with email + password, receive a JWT."""
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(data={"sub": str(user.id), "role": user.role.value})
    refresh = create_refresh_token(data={"sub": str(user.id), "role": user.role.value})
    return Token(access_token=token, refresh_token=refresh)

from pydantic import BaseModel
class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/refresh", response_model=Token)
@limiter.limit("10/minute")
async def refresh_access_token(
    request: Request,
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a valid refresh token for a new access token."""
    from jose import JWTError, jwt
    try:
        token_data = jwt.decode(payload.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if token_data.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        
        user_id = token_data.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
        
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
        
    new_access = create_access_token(data={"sub": str(user.id), "role": user.role.value})
    # We optionally could issue a new refresh token (rotation), but we'll stick to a long-lived one for simplicity here
    return Token(access_token=new_access, refresh_token=payload.refresh_token)


@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return UserRead.from_orm_user(current_user)


@router.get("/users", response_model=list[UserRead])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin", "manager")),
):
    """List all users. Admin and Manager only."""
    result = await db.execute(select(User).order_by(User.id))
    users = result.scalars().all()
    return [UserRead.from_orm_user(u) for u in users]


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    """Update a user's profile. Admin only."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "password" in update_data:
        update_data["hashed_password"] = hash_password(update_data.pop("password"))

    for field, value in update_data.items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return UserRead.from_orm_user(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    """Delete a user. Admin only. Cleans up related records first."""
    from app.models.interaction import LeadTimeline, Appointment, Task
    from app.models.lead import Lead
    from sqlalchemy import update as sa_update, delete as sa_delete

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    # Nullify leads assigned to this user
    await db.execute(
        sa_update(Lead).where(Lead.assigned_rep_id == user_id).values(assigned_rep_id=None)
    )
    # Delete timeline entries created by this user
    await db.execute(
        sa_delete(LeadTimeline).where(LeadTimeline.user_id == user_id)
    )
    # Delete appointments owned by this user
    await db.execute(
        sa_delete(Appointment).where(Appointment.user_id == user_id)
    )
    # Delete tasks assigned to or created by this user
    await db.execute(
        sa_delete(Task).where((Task.user_id == user_id) | (Task.assigned_by == user_id))
    )
    # Nullify subordinates' manager_id
    await db.execute(
        sa_update(User).where(User.manager_id == user_id).values(manager_id=None)
    )

    await db.delete(user)
    await db.commit()
    return None


# ═══════════════════════════════════════════════════════════════════════
# Google OAuth (Calendar + Tasks Sync)
# ═══════════════════════════════════════════════════════════════════════


@router.get("/google/connect")
async def google_connect(
    token: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Redirect the user to Google's OAuth consent screen.

    Pass your JWT as a query parameter: /google/connect?token=YOUR_JWT
    (needed because browser redirects can't send Authorization headers).

    After granting consent, Google redirects back to /google/callback
    with an auth code. The user's ID is passed in the OAuth `state` param.
    """
    if not token:
        raise HTTPException(status_code=401, detail="Pass your JWT as ?token=YOUR_JWT")

    from jose import JWTError, jwt as jose_jwt

    try:
        payload = jose_jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    flow = _build_google_flow()
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=str(user.id),
    )

    return RedirectResponse(url=auth_url)


@router.get("/google/callback")
async def google_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """Handle the redirect from Google after the user grants consent.

    Exchanges the auth code for access + refresh tokens, encrypts them
    with Fernet, and stores them on the user's DB row.
    """
    flow = _build_google_flow()
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI

    try:
        flow.fetch_token(code=code)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {e}")

    credentials = flow.credentials

    user_id = int(state)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.google_access_token = encrypt_token(credentials.token)
    user.google_refresh_token = encrypt_token(credentials.refresh_token)
    if credentials.expiry:
        user.google_token_expiry = credentials.expiry.replace(tzinfo=timezone.utc)

    await db.commit()

    return {
        "message": "Google account connected successfully",
        "user_id": user.id,
        "google_connected": True,
    }


@router.delete("/google/disconnect")
async def google_disconnect(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove stored Google tokens for the current user."""
    current_user.google_access_token = None
    current_user.google_refresh_token = None
    current_user.google_token_expiry = None

    await db.commit()

    return {"message": "Google account disconnected", "google_connected": False}
