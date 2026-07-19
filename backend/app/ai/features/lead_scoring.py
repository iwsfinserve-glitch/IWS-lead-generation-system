# backend/app/ai/features/lead_scoring.py
"""
LeadScoringFeature — scores a lead 0-100 and classifies it as hot/warm/cold.

Subclasses BaseAIFeature; the only additions are:
1. The response_schema (LeadScoreResult).
2. build_prompt() delegating to the prompt module.

Adding a new AI feature later looks exactly like this file.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.ai.base import BaseAIFeature
from app.ai.client import AIClient
from app.ai.prompts.lead_scoring import build_lead_scoring_context


class LeadScoreResult(BaseModel):
    """Structured result returned by LeadScoringFeature.

    This is the Pydantic model Gemini validates its JSON output against.
    It is also the Pydantic schema returned by the POST /leads/{id}/ai/score endpoint.
    """
    score: int = Field(..., ge=0, le=100, description="Lead quality score 0–100")
    label: Literal["hot", "warm", "cold"]
    reasoning: str = Field(..., description="2-4 sentence rationale for the score")
    key_signals: list[str] = Field(..., description="2-5 key signals that drove the score")
    suggested_next_action: str = Field(..., description="One actionable next step for the rep")


class LeadScoringFeature(BaseAIFeature[dict, LeadScoreResult]):
    """AI feature that scores a lead using the Gemini API.

    Context dict expected by build_prompt (all optional):
        lead_id, status, source_name, days_since_created,
        assigned_rep_name, interaction_count, interaction_breakdown,
        last_interaction_date, interaction_notes_summary,
        appointment_count, appointment_outcomes

    Usage:
        feature = LeadScoringFeature(client=ai_client)
        result: LeadScoreResult = await feature.run(context, entity_id=lead_id)
    """

    feature_name = "lead_scoring"
    response_schema = LeadScoreResult

    def build_prompt(self, context: dict) -> str:  # type: ignore[override]
        return build_lead_scoring_context(context)
