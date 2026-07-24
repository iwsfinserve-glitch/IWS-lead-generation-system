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
    AI_MODEL_NAME: str = "gemini-2.0-flash"
    AI_REPORT_MODEL_NAME: str = "gemini-2.0-pro-exp"
    AI_TEMPERATURE: float = 0.2          # Low temperature → more deterministic scoring
    AI_MAX_OUTPUT_TOKENS: int = 2048

    # Reliability
    AI_TIMEOUT_S: float = 30.0           # Per-call timeout (seconds)
    AI_MAX_RETRIES: int = 2              # Max retries for transient SDK errors

    # Feature-specific thresholds
    # Minimum dated interactions required before ContactTimingFeature calls Gemini.
    AI_MIN_INTERACTIONS: int = 1

    # Client classification thresholds — both must be met before calling Gemini.
    # AI_MIN_CLASSIFICATION_NOTES: minimum number of timeline events that contain
    #   non-empty note text (e.g. event_type='note' with a non-blank note field).
    # AI_MIN_CLASSIFICATION_NOTES_LEN: minimum combined character count of all
    #   note text — guards against short/useless notes inflating the count.
    AI_MIN_CLASSIFICATION_NOTES: int = 1
    AI_MIN_CLASSIFICATION_NOTES_LEN: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",                  # Ignore unrecognised vars (same as main config)
    )


# Module-level singleton — imported as: from app.ai.config import ai_settings
ai_settings = AISettings()
