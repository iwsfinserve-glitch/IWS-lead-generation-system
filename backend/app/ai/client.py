# backend/app/ai/client.py
"""
AIClient — thin async wrapper around the google-genai SDK.

Design principles:
- Constructor takes an injected api_key and AISettings so it is trivially
  mockable in tests (no bare module-level genai.configure() global).
- generate() runs the synchronous SDK call via asyncio.to_thread so it
  never blocks the event loop.
- JSON structured output: uses response_mime_type="application/json" +
  response_schema so Gemini returns valid JSON, then validates against the
  passed Pydantic model.
- On ValidationError: retries ONCE with a schema-correction suffix appended
  to the prompt. If still invalid: raises AIResponseParsingError.
- Transient SDK errors: manual backoff loop, capped at config.max_retries.
- Rate-limit (429 / ResourceExhausted): raises AIRateLimitError immediately
  (no point retrying — caller decides whether to surface 503).
- Logs: feature, entity_id, latency, token usage, success/failure.
  NEVER logs PII (names/email/phone) — entity_id (lead_id) only.
- plain_text=True mode: skips JSON schema — used by report generation
  which returns free prose, not structured data.
"""

import asyncio
import logging
import time
from functools import lru_cache
from typing import TypeVar, Any

from pydantic import BaseModel, ValidationError
from google import genai
from google.genai import types

from app.ai.config import AISettings, ai_settings
from app.ai.exceptions import (
    AIServiceError,
    AIRateLimitError,
    AIResponseParsingError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Strings that indicate a Gemini rate-limit / quota error
_RATE_LIMIT_SIGNALS = ("429", "resource_exhausted", "quota", "rate limit", "too many")


def _is_rate_limit_error(exc: Exception) -> bool:
    """Heuristic: check exception message for rate-limit signals."""
    msg = str(exc).lower()
    return any(sig in msg for sig in _RATE_LIMIT_SIGNALS)


class AIClient:
    """Async gateway to the Gemini generative AI API.

    Usage (as a FastAPI dependency):
        client: AIClient = Depends(get_ai_client)
        result = await client.generate(
            prompt=my_prompt,
            response_schema=MyPydanticModel,
            feature_name="lead_scoring",
            entity_id=lead_id,
        )
    """

    def __init__(self, api_key: str, config: AISettings | None = None) -> None:
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not configured. "
                "Add it to backend/.env to enable AI features."
            )
        self._sdk = genai.Client(api_key=api_key)
        self._config = config or ai_settings

    # ── Internal helpers ────────────────────────────────────────────────

    def _build_gen_config(
        self,
        response_schema: type[BaseModel] | None,
        temperature: float,
        plain_text: bool,
    ) -> types.GenerateContentConfig:
        """Build a GenerateContentConfig for either JSON-structured or plain-text output."""
        if plain_text or response_schema is None:
            return types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=self._config.AI_MAX_OUTPUT_TOKENS,
            )
        return types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=temperature,
            max_output_tokens=self._config.AI_MAX_OUTPUT_TOKENS,
        )

    async def _sdk_call(
        self, prompt: str, gen_config: types.GenerateContentConfig, retries: int = 2, model_name: str | None = None
    ):
        """Single SDK call via asyncio.to_thread. Handles rate limits with backoff. Raises AIServiceError on failure."""
        import asyncio
        for attempt in range(retries + 1):
            try:
                return await asyncio.to_thread(
                    self._sdk.models.generate_content,
                    model=model_name or self._config.AI_MODEL_NAME,
                    contents=prompt,
                    config=gen_config,
                )
            except Exception as exc:
                if _is_rate_limit_error(exc):
                    if attempt < retries:
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    raise AIRateLimitError(f"Gemini rate limit exceeded: {exc}") from exc
                raise AIServiceError(f"Gemini SDK call failed: {exc}") from exc

    # ── Public API ──────────────────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        response_schema: type[T] | None = None,
        temperature: float | None = None,
        feature_name: str = "unknown",
        entity_id: int | str = "",
        plain_text: bool = False,
        model_name: str | None = None,
    ) -> Any:
        """Call Gemini and return a validated Pydantic model instance.

        Args:
            prompt:          Full prompt string.
            response_schema: Pydantic model class — used as Gemini's response_schema
                             in JSON mode and for validation.
            temperature:     Override the default AI_TEMPERATURE for this call.
            feature_name:    Logged for observability; no PII.
            entity_id:       The lead_id / entity being processed; logged, no PII.
            plain_text:      True for free-text responses (reports). Skips JSON
                             schema and validation; response_schema must have a
                             `text: str` field.

        Returns:
            An instance of response_schema populated from the Gemini response.

        Raises:
            AIRateLimitError:       Gemini returned 429 / quota exceeded.
            AIResponseParsingError: JSON validation failed after one retry.
            AIServiceError:         Any other Gemini/network failure.
        """
        temp = temperature if temperature is not None else self._config.AI_TEMPERATURE
        gen_config = self._build_gen_config(response_schema, temp, plain_text)
        start = time.monotonic()

        # ── Transient-error retry loop (SDK-level failures) ──────────────
        response = None
        last_service_exc: AIServiceError | None = None

        for attempt in range(self._config.AI_MAX_RETRIES + 1):
            try:
                response = await self._sdk_call(prompt, gen_config, model_name=model_name)
                break  # Success — exit retry loop
            except AIRateLimitError:
                # Rate limits are not transient in the normal sense — surface immediately
                latency_ms = int((time.monotonic() - start) * 1000)
                logger.warning(
                    "[AI] feature=%s entity_id=%s latency=%dms status=rate_limit",
                    feature_name, entity_id, latency_ms,
                )
                raise
            except AIServiceError as exc:
                last_service_exc = exc
                if attempt < self._config.AI_MAX_RETRIES:
                    backoff = 0.5 * (2 ** attempt)  # 0.5s, 1.0s, …
                    logger.warning(
                        "[AI] feature=%s entity_id=%s attempt=%d retrying in %.1fs",
                        feature_name, entity_id, attempt, backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue
                # Exhausted retries — re-raise last error
                latency_ms = int((time.monotonic() - start) * 1000)
                logger.error(
                    "[AI] feature=%s entity_id=%s latency=%dms status=fail err=%s",
                    feature_name, entity_id, latency_ms, type(exc).__name__,
                )
                raise

        # ── Plain-text mode (report generation) ─────────────────────────
        if plain_text:
            latency_ms = int((time.monotonic() - start) * 1000)
            self._log_success(feature_name, entity_id, latency_ms, response)
            # response_schema must be a model with a `text` field (e.g. ReportText)
            return response_schema(text=response.text)  # type: ignore[call-arg]

        # ── JSON mode: validate response against Pydantic schema ─────────
        try:
            result = response_schema.model_validate_json(response.text)
        except ValidationError:
            # One-shot retry: append schema-correction instruction to the original prompt
            correction_prompt = (
                prompt
                + "\n\nYour last response did not match the required JSON schema. "
                "Return only valid JSON that exactly matches the schema — no extra keys, "
                "no prose, no markdown fences."
            )
            try:
                response = await self._sdk_call(correction_prompt, gen_config)
                result = response_schema.model_validate_json(response.text)
            except ValidationError as exc2:
                latency_ms = int((time.monotonic() - start) * 1000)
                logger.error(
                    "[AI] feature=%s entity_id=%s latency=%dms status=parse_fail",
                    feature_name, entity_id, latency_ms,
                )
                raise AIResponseParsingError(
                    "Gemini response did not match the expected schema after retry."
                ) from exc2
            except AIServiceError:
                raise  # Let the SDK error propagate as-is

        latency_ms = int((time.monotonic() - start) * 1000)
        self._log_success(feature_name, entity_id, latency_ms, response)
        return result

    def _log_success(
        self, feature_name: str, entity_id: int | str, latency_ms: int, response
    ) -> None:
        """Log a successful AI call. Extracts token usage if available."""
        tokens = None
        try:
            tokens = response.usage_metadata.total_token_count
        except Exception:
            pass
        logger.info(
            "[AI] feature=%s entity_id=%s latency=%dms tokens=%s status=ok",
            feature_name, entity_id, latency_ms, tokens,
        )


# ── FastAPI dependency ───────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _build_ai_client() -> AIClient:
    """Build the AIClient singleton (called once, cached by lru_cache)."""
    # Import here to avoid circular imports at module load time
    from app.core.config import settings  # noqa: PLC0415
    return AIClient(api_key=settings.GEMINI_API_KEY, config=ai_settings)


def get_ai_client() -> AIClient:
    """FastAPI dependency — returns the cached AIClient singleton.

    Usage in a route:
        client: AIClient = Depends(get_ai_client)
    """
    return _build_ai_client()
