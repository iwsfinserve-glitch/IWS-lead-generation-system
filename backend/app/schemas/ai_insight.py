# backend/app/schemas/ai_insight.py
"""
Pydantic schemas for the AI insights API layer.

LeadScoreRead            — response from GET /leads/{id}/ai/score
ContactTimingRead        — response from GET /leads/{id}/ai/contact-timing
ClientClassificationRead — response from GET /leads/{id}/ai/client-classification
AIUnavailableResponse    — returned when the AI service is unavailable (503 body)
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LeadScoreRead(BaseModel):
    """Full scoring result returned by the GET endpoint.

    Mirrors LeadScoreResult fields plus the persistence metadata
    (generated_at, model_used) from the LeadAIInsight row.
    """
    score: int = Field(..., ge=0, le=100)
    label: Literal["hot", "warm", "cold"]
    reasoning: str
    key_signals: list[str]
    suggested_next_action: str
    generated_at: datetime
    model_used: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_insight(cls, insight) -> "LeadScoreRead":
        """Construct from a LeadAIInsight ORM row (insight_type='score')."""
        payload = insight.payload
        return cls(
            score=payload["score"],
            label=payload["label"],
            reasoning=payload["reasoning"],
            key_signals=payload["key_signals"],
            suggested_next_action=payload["suggested_next_action"],
            generated_at=insight.generated_at,
            model_used=insight.model_used,
        )


class ContactTimingRead(BaseModel):
    """Contact-timing result returned by the GET endpoint.

    Mirrors ContactTimingResult fields plus persistence metadata.
    has_sufficient_data=False means the sparse-data guard fired and no
    Gemini call was made — show a muted "not enough history" note in the UI.
    """
    has_sufficient_data: bool
    suggested_days: list[str]
    suggested_window: str | None
    confidence: Literal["low", "medium", "high"]
    reasoning: str
    generated_at: datetime
    model_used: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_insight(cls, insight) -> "ContactTimingRead":
        """Construct from a LeadAIInsight ORM row (insight_type='contact_timing')."""
        payload = insight.payload
        return cls(
            has_sufficient_data=payload["has_sufficient_data"],
            suggested_days=payload.get("suggested_days", []),
            suggested_window=payload.get("suggested_window"),
            confidence=payload["confidence"],
            reasoning=payload["reasoning"],
            generated_at=insight.generated_at,
            model_used=insight.model_used,
        )


class AIUnavailableResponse(BaseModel):
    """Response body when the AI service returns a 503."""
    available: bool = False
    detail: str = "AI service is temporarily unavailable. Please try again later."


class ClientClassificationRead(BaseModel):
    """Client-classification result returned by the GET/POST endpoint.

    has_sufficient_data=False means the sparse-data guard fired: not enough
    substantive notes exist yet, no Gemini call was made, and classification
    is None. The UI should show a neutral 'Gathering data...' indicator.
    """
    has_sufficient_data: bool
    classification: str | None          # "hni" | "professional" | "retail" | None
    confidence: Literal["low", "medium", "high"]
    reasoning: str
    key_indicators: list[str]
    generated_at: datetime
    model_used: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_insight(cls, insight) -> "ClientClassificationRead":
        """Construct from a LeadAIInsight ORM row (insight_type='client_classification')."""
        payload = insight.payload
        return cls(
            has_sufficient_data=payload["has_sufficient_data"],
            classification=payload.get("classification"),
            confidence=payload.get("confidence", "low"),
            reasoning=payload.get("reasoning", ""),
            key_indicators=payload.get("key_indicators", []),
            generated_at=insight.generated_at,
            model_used=insight.model_used,
        )
