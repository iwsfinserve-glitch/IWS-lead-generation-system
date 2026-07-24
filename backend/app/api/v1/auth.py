"""
Auth routes — registration, login, user listing, and Google OAuth connection.
"""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.responses import RedirectResponse, JSONResponse
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

# Allow OAuth locally over HTTP
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

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
        autogenerate_code_verifier=False,
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
        phone_number=payload.phone_number,
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


@router.get("/sales-reps", response_model=list[UserRead])
async def list_sales_reps(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all users with the sales_rep role. Accessible to any authenticated user.

    Used by the lead transfer form so sales reps can see who they can
    transfer a lead to without requiring admin/manager privilege.
    """
    result = await db.execute(
        select(User).where(User.role == UserRole.sales_rep).order_by(User.name)
    )
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
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Handle the redirect from Google after the user grants consent.

    Flow:
      1. Exchange the auth code for Google access + refresh tokens.
      2. Encrypt the tokens with Fernet and store them on the user record.
      3. Kick off a background job to bulk-sync all existing CRM appointments
         into the user's Google Calendar.
      4. Redirect the user back to the Streamlit frontend Appointments page
         with a `google_connected=1` query param so the UI can show a toast.
    """
    flow = _build_google_flow()
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI

    try:
        flow.fetch_token(code=code)
    except Exception as e:
        import logging
        import urllib.parse
        logging.error(f"Google OAuth token exchange failed: {e}", exc_info=True)
        # Redirect to frontend with an error flag and the error message URL-encoded.
        frontend_url = settings.GOOGLE_REDIRECT_URI.replace(
            "/api/v1/auth/google/callback", ""
        ).replace("8000", "5173")
        error_msg = urllib.parse.quote(str(e))
        return RedirectResponse(
            url=f"{frontend_url}/appointments?google_error=1&error_msg={error_msg}"
        )

    credentials = flow.credentials

    # Parse user_id out of the opaque state string.
    # The state was set to the plain user ID in /google/connect.
    try:
        user_id = int(state)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.google_access_token = encrypt_token(credentials.token)
    # Google only issues a refresh_token on the *first* authorization or when
    # prompt=consent is used.  Guard against it being None.
    if credentials.refresh_token:
        user.google_refresh_token = encrypt_token(credentials.refresh_token)
    if credentials.expiry:
        user.google_token_expiry = credentials.expiry.replace(tzinfo=timezone.utc)

    await db.commit()

    # Kick off the bulk back-fill in the background - this does NOT block the redirect.
    from app.services.google_sync import bulk_sync_all_appointments
    background_tasks.add_task(bulk_sync_all_appointments, user.id)

    # Determine the Streamlit frontend URL from the configured redirect URI
    # e.g. http://localhost:8000/api/v1/auth/google/callback
    #   -> http://localhost:8501
    frontend_base = (
        settings.GOOGLE_REDIRECT_URI
        .split("/api/")[0]           # strip the path
        .replace(":8000", ":5173")  # swap backend port for frontend React port
    )
    redirect_target = f"{frontend_base}/appointments?google_connected=1"
    return RedirectResponse(url=redirect_target, status_code=302)


@router.delete("/google/disconnect", status_code=status.HTTP_200_OK)
async def google_disconnect(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove stored Google tokens for the current user.

    Does NOT revoke the token on Google's side - users should do that via
    their Google Account security settings if desired.
    """
    current_user.google_access_token = None
    current_user.google_refresh_token = None
    current_user.google_token_expiry = None

    await db.commit()

    return {"message": "Google account disconnected", "google_connected": False}


@router.get("/google/status")
async def google_status(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return whether the current user has Google Calendar connected.

    Lightweight endpoint - does not hit the Google API.
    """
    return {
        "google_connected": current_user.google_refresh_token is not None,
        "user_id": current_user.id,
    }


@router.post("/google/sync-appointments", status_code=status.HTTP_202_ACCEPTED)
async def trigger_google_calendar_sync(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Manually trigger a bulk back-fill of all CRM appointments to Google Calendar.

    Returns immediately (202 Accepted) and performs the sync in the background.
    Requires the user to have already connected their Google account.
    """
    if not current_user.google_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Calendar is not connected. Connect via /auth/google/connect first.",
        )

    from app.services.google_sync import bulk_sync_all_appointments
    background_tasks.add_task(bulk_sync_all_appointments, current_user.id)

    return {
        "message": "Calendar sync started in the background.",
        "user_id": current_user.id,
    }
