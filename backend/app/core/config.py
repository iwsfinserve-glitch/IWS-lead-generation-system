"""
Application Settings — Single source of truth for all configuration.

Uses pydantic-settings to load values from the .env file at the backend root.
Every other module imports `settings` from here instead of reading env vars directly.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All configuration is driven by environment variables (or the .env file).
    Pydantic validates types at startup — if DATABASE_URL is missing,
    the app will refuse to boot with a clear error message.
    """

    # ── PostgreSQL (async driver) ──────────────────────────────────────
    # Example: postgresql+asyncpg://postgres:postgres@localhost:5432/lead_crm
    DATABASE_URL: str

    # ── JWT Authentication ─────────────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120

    # ── Google OAuth 2.0 (Workspace calendar/task sync) ────────────────
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"

    # ── Fernet Encryption (for Google tokens stored at rest) ───────────
    ENCRYPTION_KEY: str = ""

    # ── Gemini AI (report generation) ──────────────────────────────────
    GEMINI_API_KEY: str = ""

    # ── Pydantic-settings config ───────────────────────────────────────
    # Tells pydantic-settings to read from the .env file located one
    # directory above this file (backend/.env relative to backend/app/core/).
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # If a var exists both in the real environment AND the .env file,
        # the real environment wins. This lets Docker/CI override .env values.
        extra="ignore",
    )


# Singleton — imported everywhere as `from app.core.config import settings`
settings = Settings()
