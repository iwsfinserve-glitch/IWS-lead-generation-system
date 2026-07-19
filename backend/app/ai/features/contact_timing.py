# backend/app/ai/features/contact_timing.py
"""
ContactTimingFeature — determines the best day(s) and time window to reach a lead.

Key behaviour:
- Sparse-data guard in run(): if interaction_count < AI_MIN_INTERACTIONS,
  returns ContactTimingResult(has_sufficient_data=False, ...) immediately
  WITHOUT calling Gemini — preventing confident-sounding hallucination on
  empty history.
- When data is sufficient, delegates to AIClient exactly like LeadScoringFeature.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.ai.base import BaseAIFeature
from app.ai.client import AIClient
from app.ai.config import ai_settings
from app.ai.prompts.contact_timing import build_contact_timing_context


class ContactTimingResult(BaseModel):
    """Structured result returned by ContactTimingFeature.

    Also used as the Pydantic schema Gemini validates its JSON output against,
    and as the API response body for GET /leads/{id}/ai/contact-timing.
    """
    has_sufficient_data: bool
    suggested_days: list[str] = Field(
        default_factory=list,
        description="Day names with most interactions, e.g. ['Tuesday', 'Thursday']",
    )
    suggested_window: str | None = Field(
        None,
        description="24-hour time range string, e.g. '10:00–12:00'. Null if data is sparse.",
    )
    confidence: Literal["low", "medium", "high"]
    reasoning: str = Field(..., description="2-3 sentence factual rationale")


class ContactTimingFeature(BaseAIFeature[dict, ContactTimingResult]):
    """AI feature that identifies the optimal contact window for a lead.

    Context dict expected by build_prompt:
        interaction_count    int   — total timeline entries (checked by guard)
        interaction_events   list  — [{event_type, day_name, time_str, date_str}]
        appointment_events   list  — [{title, day_name, time_str, date_str}]

    Usage:
        feature = ContactTimingFeature(client=ai_client)
        result: ContactTimingResult = await feature.run(context, entity_id=lead_id)
    """

    feature_name = "contact_timing"
    response_schema = ContactTimingResult

    def build_prompt(self, context: dict) -> str:  # type: ignore[override]
        return build_contact_timing_context(context)

    async def run(  # type: ignore[override]
        self, context: dict, entity_id: int | str = ""
    ) -> ContactTimingResult:
        """Execute the feature with a sparse-data guard.

        If interaction_count < AI_MIN_INTERACTIONS, returns a
        has_sufficient_data=False result immediately — no Gemini call is made.
        This prevents the model from hallucinating a plausible-sounding window
        when there is no real signal in the data.
        """
        interaction_count = context.get("interaction_count", 0)
        threshold = ai_settings.AI_MIN_INTERACTIONS

        if interaction_count < threshold:
            return ContactTimingResult(
                has_sufficient_data=False,
                suggested_days=[],
                suggested_window=None,
                confidence="low",
                reasoning=(
                    f"Not enough interaction history yet — {interaction_count} "
                    f"interaction(s) recorded, minimum {threshold} required for a "
                    "reliable contact-time recommendation."
                ),
            )

        # Sufficient data — delegate to AIClient via parent run()
        return await super().run(context, entity_id=entity_id)
