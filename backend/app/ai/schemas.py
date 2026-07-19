# backend/app/ai/schemas.py
"""
Shared Pydantic schemas used across the AI layer.

Feature-specific result schemas (LeadScoreResult, ContactTimingResult, etc.)
live in their respective features/ module.  This file holds the common
envelope and any cross-feature types.
"""

from datetime import datetime
from pydantic import BaseModel


class AIInsightEnvelope(BaseModel):
    """API response wrapper returned from GET /leads/{id}/ai/* endpoints.

    Routes construct this from a LeadAIInsight ORM row.
    """
    insight_type: str
    payload: dict
    score: float | None = None
    confidence: float | None = None
    model_used: str
    generated_at: datetime

    model_config = {"from_attributes": True}


class ReportText(BaseModel):
    """Thin wrapper so ReportGenerationFeature fits the BaseAIFeature[..., TResult] contract.
    
    AIClient.generate(plain_text=True) instantiates this with text=response.text.
    The text field is then extracted by the report generation service.
    """
    text: str
