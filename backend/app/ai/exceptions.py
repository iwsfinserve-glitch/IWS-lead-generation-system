# backend/app/ai/exceptions.py
"""
AI-specific exception hierarchy.

AIServiceError          — base; wraps any Gemini SDK failure
AIRateLimitError        — 429 / quota exhausted from Gemini
AIResponseParsingError  — response did not match the expected JSON schema after retry
AIInsufficientDataError — sparse-data guard fired; caller should not call Gemini
"""


class AIServiceError(Exception):
    """Base exception for all AI service failures."""
    pass


class AIRateLimitError(AIServiceError):
    """Raised when Gemini returns a rate-limit / quota-exhausted error (HTTP 429)."""
    pass


class AIResponseParsingError(AIServiceError):
    """Raised when the Gemini response cannot be parsed into the expected Pydantic schema
    even after the one-shot schema-correction retry."""
    pass


class AIInsufficientDataError(AIServiceError):
    """Raised when a feature's pre-condition check determines there is not enough data
    to produce a meaningful AI result (e.g. fewer interactions than threshold)."""
    pass
