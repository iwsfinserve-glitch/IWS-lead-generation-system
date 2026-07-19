"""
Application Settings — Single source of truth for all configuration.

Uses pydantic-settings to load values from the .env file at the backend root.
Every other module imports `settings` from here instead of reading env vars directly.
"""

import logging
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_config_logger = logging.getLogger(__name__)


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

    @field_validator("SECRET_KEY", mode="before")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Strip whitespace and warn if the key is too short for production."""
        v = v.strip()
        if len(v) < 4:
            raise ValueError(
                "SECRET_KEY must be at least 4 characters. "
                "Generate a strong key with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        if len(v) < 32:
            _config_logger.warning(
                "SECRET_KEY is shorter than 32 characters. "
                "This is insecure for production — consider using a stronger key."
            )
        return v

    # ── Google OAuth 2.0 (Workspace calendar/task sync) ────────────────
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"

    # ── Fernet Encryption (for Google tokens stored at rest) ───────────
    ENCRYPTION_KEY: str = ""

    # ── Gemini AI (report generation) ──────────────────────────────────
    GEMINI_API_KEY: str = ""

    # ── CORS ───────────────────────────────────────────────────────────
    # Comma-separated list of allowed origins. Default permits the local
    # Streamlit dev server. Override in .env for production.
    ALLOWED_ORIGINS: str = "http://localhost:8501,http://localhost:8000"

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse the comma-separated ALLOWED_ORIGINS into a list."""
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

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
