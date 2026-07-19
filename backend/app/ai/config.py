# backend/app/ai/config.py
"""
AI-specific settings — separate BaseSettings subclass so AI knobs
can be tuned via .env without touching the main app config.

All env-var names are prefixed with AI_ to avoid collisions.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class AISettings(BaseSettings):
    """Pydantic-settings model for AI feature configuration.

    Every value can be overridden by a matching env variable or .env entry.
    """

    # Model & generation params
    AI_MODEL_NAME: str = "gemini-3.5-flash"
    AI_TEMPERATURE: float = 0.2          # Low temperature → more deterministic scoring
    AI_MAX_OUTPUT_TOKENS: int = 2048

    # Reliability
    AI_TIMEOUT_S: float = 30.0           # Per-call timeout (seconds)
    AI_MAX_RETRIES: int = 2              # Max retries for transient SDK errors

    # Feature-specific thresholds
    # Minimum dated interactions required before ContactTimingFeature calls Gemini.
    AI_MIN_INTERACTIONS: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",                  # Ignore unrecognised vars (same as main config)
    )


# Module-level singleton — imported as: from app.ai.config import ai_settings
ai_settings = AISettings()
