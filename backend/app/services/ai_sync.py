"""
AI Background Sync — Automatic lead scoring and contact-timing analysis.

Designed to run via FastAPI BackgroundTasks whenever interaction events occur
(e.g. note added, status updated, appointment created/updated/deleted).
Runs in its own short-lived database session and logs gracefully on failure.
"""

import logging
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import async_session_factory
from app.db.base import Lead
from app.models.ai_insight import LeadAIInsight
from app.ai.client import get_ai_client
from app.ai.config import ai_settings
from app.ai.features.lead_scoring import LeadScoringFeature, LeadScoreResult
from app.ai.features.contact_timing import ContactTimingFeature, ContactTimingResult
from app.ai.features.client_classification import ClientClassificationFeature, ClientClassificationResult
from app.ai.exceptions import AIServiceError

logger = logging.getLogger(__name__)


async def trigger_ai_analysis_background(lead_id: int) -> None:
    """Run AI scoring and contact-timing analysis in the background for a lead.

    Loads lead relationships, calls Gemini features, persists LeadAIInsight rows,
    and updates denormalized AI fields on the Lead table.
    """
    ai_client = get_ai_client()
    if not ai_client:
        logger.warning("AI client unavailable during background analysis for lead_id=%d", lead_id)
        return

    # Import context builders from ai_insights to avoid code duplication
    from app.api.v1.ai_insights import _build_lead_scoring_context, _build_contact_timing_context

    async with async_session_factory() as db:
        try:
            result = await db.execute(
                select(Lead)
                .where(Lead.id == lead_id)
                .options(
                    selectinload(Lead.timeline),
                    selectinload(Lead.appointments),
                    selectinload(Lead.source),
                    selectinload(Lead.assigned_rep),
                )
            )
            lead = result.scalar_one_or_none()
            if not lead:
                logger.warning("Lead %d not found during background AI analysis", lead_id)
                return

            now = datetime.now(timezone.utc)

            # ── 1. Run Lead Scoring ──────────────────────────────────────────
            try:
                score_context = await _build_lead_scoring_context(lead, db)
                scoring_feature = LeadScoringFeature(client=ai_client)
                score_res: LeadScoreResult = await scoring_feature.run(score_context, entity_id=lead_id)

                score_insight = LeadAIInsight(
                    lead_id=lead_id,
                    insight_type="score",
                    payload=score_res.model_dump(),
                    score=float(score_res.score),
                    confidence=None,
                    model_used=ai_settings.AI_MODEL_NAME,
                    generated_at=now,
                )
                db.add(score_insight)

                lead.ai_score = float(score_res.score)
                lead.ai_score_label = score_res.label
                lead.ai_score_updated_at = now
                logger.info("Background AI scoring completed for lead %d: %s (%s)", lead_id, score_res.score, score_res.label)
            except AIServiceError as exc:
                logger.warning("Background AI scoring failed for lead %d: %s", lead_id, exc)
            except Exception:
                logger.exception("Unexpected error during background AI scoring for lead %d", lead_id)

            import asyncio
            await asyncio.sleep(1)

            # ── 2. Run Contact Timing ────────────────────────────────────────
            try:
                timing_context = await _build_contact_timing_context(lead, db)
                timing_feature = ContactTimingFeature(client=ai_client)
                timing_res: ContactTimingResult = await timing_feature.run(timing_context, entity_id=lead_id)

                timing_insight = LeadAIInsight(
                    lead_id=lead_id,
                    insight_type="contact_timing",
                    payload=timing_res.model_dump(),
                    score=None,
                    confidence=None,
                    model_used=ai_settings.AI_MODEL_NAME,
                    generated_at=now,
                )
                db.add(timing_insight)
                logger.info("Background AI contact-timing completed for lead %d", lead_id)
            except AIServiceError as exc:
                logger.warning("Background AI contact-timing failed for lead %d: %s", lead_id, exc)
            except Exception:
                logger.exception("Unexpected error during background AI contact-timing for lead %d", lead_id)

            # ── 3. Run Client Classification (only if currently unclassified) ────────
            # Quota control: once a lead is classified, automatic background
            # checks stop. Re-classification only happens via the manual
            # POST /leads/{id}/ai/client-classification endpoint.
            if lead.client_classification is None:
                try:
                    from app.api.v1.ai_insights import _build_classification_context
                    cls_context = await _build_classification_context(lead, db)
                    cls_feature = ClientClassificationFeature(client=ai_client)
                    cls_res: ClientClassificationResult = await cls_feature.run(cls_context, entity_id=lead_id)

                    cls_insight = LeadAIInsight(
                        lead_id=lead_id,
                        insight_type="client_classification",
                        payload=cls_res.model_dump(),
                        score=None,
                        confidence=None,
                        model_used=ai_settings.AI_MODEL_NAME,
                        generated_at=now,
                    )
                    db.add(cls_insight)

                    if cls_res.has_sufficient_data and cls_res.classification:
                        lead.client_classification = cls_res.classification
                        lead.client_classification_updated_at = now
                        logger.info(
                            "Background classification completed for lead %d: %s (%s)",
                            lead_id, cls_res.classification, cls_res.confidence,
                        )
                    else:
                        logger.info(
                            "Background classification skipped for lead %d: insufficient data (%d notes)",
                            lead_id, len(cls_context.get("note_entries", [])),
                        )
                except AIServiceError as exc:
                    logger.warning("Background classification failed for lead %d: %s", lead_id, exc)
                except Exception:
                    logger.exception("Unexpected error during background classification for lead %d", lead_id)
            else:
                logger.debug(
                    "Background classification skipped for lead %d: already classified as '%s'",
                    lead_id, lead.client_classification,
                )

            await db.commit()

        except Exception:
            logger.exception("Background AI analysis session failed for lead %d", lead_id)
            await db.rollback()

async def trigger_classification_background(lead_id: int) -> None:
    """Helper for manual re-classification, bypassing the 'unclassified' check."""
    ai_client = get_ai_client()
    if not ai_client:
        return

    from app.api.v1.ai_insights import _build_classification_context

    async with async_session_factory() as db:
        lead = await db.get(Lead, lead_id)
        if not lead:
            return

        try:
            cls_context = await _build_classification_context(lead, db)
            cls_feature = ClientClassificationFeature(client=ai_client)
            cls_res: ClientClassificationResult = await cls_feature.run(cls_context, entity_id=lead_id)

            now = datetime.now(timezone.utc)
            cls_insight = LeadAIInsight(
                lead_id=lead_id,
                insight_type="client_classification",
                payload=cls_res.model_dump(),
                score=None,
                confidence=None,
                model_used=ai_settings.AI_MODEL_NAME,
                generated_at=now,
            )
            db.add(cls_insight)

            if cls_res.has_sufficient_data and cls_res.classification:
                lead.client_classification = cls_res.classification
                lead.client_classification_updated_at = now
            
            await db.commit()
        except Exception:
            logger.exception("Manual re-classification failed for lead %d", lead_id)
            await db.rollback()
