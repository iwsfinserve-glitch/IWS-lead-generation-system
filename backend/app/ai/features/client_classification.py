# backend/app/ai/features/client_classification.py
"""
ClientClassificationFeature — classifies a lead as 'hni', 'professional', or 'retail'.

Key behaviour:
- Sparse-data guard in run(): checks that the lead has at least
  AI_MIN_CLASSIFICATION_NOTES timeline events that contain non-empty note text,
  AND that the combined note length meets AI_MIN_CLASSIFICATION_NOTES_LEN.
  If either threshold is unmet, returns ClientClassificationResult(
      has_sufficient_data=False, classification=None, ...) immediately — no
  Gemini call is made.  This prevents confident-sounding guesses on empty history
  and mirrors the ContactTimingFeature pattern exactly.
- Allows downgrading: the feature always returns the freshest classification;
  callers decide whether to overwrite the stored value (they should).
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.ai.base import BaseAIFeature
from app.ai.client import AIClient
from app.ai.config import ai_settings
from app.ai.prompts.client_classification import build_client_classification_context


class ClientClassificationResult(BaseModel):
    """Structured result returned by ClientClassificationFeature.

    Also used as the Pydantic schema Gemini validates its JSON output against,
    and as the core payload stored in LeadAIInsight for insight_type='client_classification'.
    """

    has_sufficient_data: bool = Field(
        ...,
        description="False when the sparse-data guard fired — no Gemini call was made.",
    )
    classification: Literal["hni", "professional", "retail"] | None = Field(
        None,
        description="Client tier. None when has_sufficient_data is False.",
    )
    confidence: Literal["low", "medium", "high"] = Field(
        "low",
        description="Model's self-assessed confidence in the classification.",
    )
    reasoning: str = Field(
        ...,
        description="2-3 sentence factual rationale citing specific signals.",
    )
    key_indicators: list[str] = Field(
        default_factory=list,
        description="2-5 specific triggers from interaction notes / profile.",
    )


class ClientClassificationFeature(BaseAIFeature[dict, ClientClassificationResult]):
    """AI feature that classifies a lead into hni / professional / retail.

    Context dict expected by build_prompt:
        lead_name            str
        profession           str | None
        address              str | None
        status               str
        source_name          str | None
        days_since_created   int
        assigned_rep_name    str | None
        note_entries         list[dict]  [{date_str, note_text}]
        notes_char_count     int         combined length of all note text
        appointment_count    int
        appointment_outcomes list[str]

    Usage:
        feature = ClientClassificationFeature(client=ai_client)
        result: ClientClassificationResult = await feature.run(context, entity_id=lead_id)
    """

    feature_name = "client_classification"
    response_schema = ClientClassificationResult

    def build_prompt(self, context: dict) -> str:  # type: ignore[override]
        return build_client_classification_context(context)

    async def run(  # type: ignore[override]
        self,
        context: dict,
        entity_id: int | str = "",
    ) -> ClientClassificationResult:
        """Execute the feature with a sparse-data guard.

        Two-part guard (both must pass before we call Gemini):
          1. note_count >= AI_MIN_CLASSIFICATION_NOTES
             (enough interaction events with substantive note text)
          2. notes_char_count >= AI_MIN_CLASSIFICATION_NOTES_LEN
             (combined notes are long enough to contain real signal)

        If either threshold is unmet, returns has_sufficient_data=False
        immediately — no Gemini API credit is consumed.
        """
        note_count: int = len(context.get("note_entries", []))
        notes_char_count: int = context.get("notes_char_count", 0)

        min_notes = ai_settings.AI_MIN_CLASSIFICATION_NOTES
        min_len = ai_settings.AI_MIN_CLASSIFICATION_NOTES_LEN

        if note_count < min_notes or notes_char_count < min_len:
            short_reason = (
                f"Not enough interaction data to classify yet — "
                f"{note_count} note(s) totalling {notes_char_count} character(s) recorded; "
                f"minimum required: {min_notes} note(s) and {min_len} characters combined. "
                "Add more detailed interaction notes to unlock AI classification."
            )
            return ClientClassificationResult(
                has_sufficient_data=False,
                classification=None,
                confidence="low",
                reasoning=short_reason,
                key_indicators=[],
            )

        # Sufficient data — delegate to AIClient via parent run()
        return await super().run(context, entity_id=entity_id)
