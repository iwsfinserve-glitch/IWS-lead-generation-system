# backend/app/ai/base.py
"""
BaseAIFeature — the abstract base class every AI feature subclasses.

Adding a new AI feature = 1 prompt module + 1 subclass here (~30 lines).
No changes to AIClient required.

Generic parameters:
    TContext — the input type (usually dict with lead data)
    TResult  — a Pydantic BaseModel subclass returned by generate()
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydantic import BaseModel

from app.ai.client import AIClient
from app.ai.exceptions import AIServiceError  # re-exported for subclass convenience

TContext = TypeVar("TContext")
TResult = TypeVar("TResult", bound=BaseModel)


class BaseAIFeature(ABC, Generic[TContext, TResult]):
    """Abstract base for all AI features.

    Subclass contract:
        1. Set `feature_name: str` (used in logs)
        2. Set `response_schema: type[TResult]` (Pydantic model class)
        3. Implement `build_prompt(context) -> str`

    That's it. `run()` handles the client call, logging, and error propagation.
    Feature-specific branching MUST NOT go into AIClient.

    Example subclass:
        class LeadScoringFeature(BaseAIFeature[dict, LeadScoreResult]):
            feature_name = "lead_scoring"
            response_schema = LeadScoreResult

            def build_prompt(self, context: dict) -> str:
                return build_lead_scoring_context(context)
    """

    feature_name: str = ""
    response_schema: type[TResult]  # type: ignore[misc]

    def __init__(self, client: AIClient) -> None:
        self.client = client

    @abstractmethod
    def build_prompt(self, context: TContext) -> str:
        """Build the full prompt string from the structured context.

        Implementations live in app/ai/prompts/<feature>.py and are
        imported here — keeps prompt text out of business logic.
        """
        ...

    async def run(self, context: TContext, entity_id: int | str = "", model_name: str | None = None) -> TResult:
        """Execute the AI feature end-to-end.

        Calls build_prompt → client.generate → returns validated result.
        On AIServiceError (including subclasses): re-raises — callers decide
        whether to return 503, a fallback value, or propagate further.
        """
        prompt = self.build_prompt(context)
        return await self.client.generate(
            prompt=prompt,
            response_schema=self.response_schema,
            feature_name=self.feature_name,
            entity_id=entity_id,
            model_name=model_name,
        )
