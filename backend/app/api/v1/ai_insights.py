# backend/app/api/v1/ai_insights.py
"""
AI Insights routes — lead scoring (Phase 1) and contact timing (Phase 2).

Mounted at /api/v1 by main.py, so routes resolve to:
    POST /api/v1/leads/{lead_id}/ai/score
    GET  /api/v1/leads/{lead_id}/ai/score

Auth: same RBAC as viewing the lead — sales reps see own leads,
      managers/admins see all — reuses _get_lead_or_404 + _check_lead_access
      (inlined here to avoid a circular import with leads.py).
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.base import Lead
from app.models.ai_insight import LeadAIInsight
from app.models.user import User
from app.ai.client import AIClient, get_ai_client
from app.ai.config import ai_settings
from app.ai.features.lead_scoring import LeadScoringFeature, LeadScoreResult
from app.ai.features.contact_timing import ContactTimingFeature, ContactTimingResult
from app.ai.exceptions import AIServiceError
from app.schemas.ai_insight import LeadScoreRead, ContactTimingRead, AIUnavailableResponse
from app.api.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leads", tags=["AI Insights"])


# ── RBAC helpers (mirrors leads.py — inlined to avoid circular import) ───────

async def _get_lead_or_404(lead_id: int, db: AsyncSession) -> Lead:
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


def _check_lead_access(lead: Lead, user: User) -> None:
    """Sales reps can only access their own assigned leads."""
    if user.role.value == "sales_rep" and lead.assigned_rep_id != user.id:
        raise HTTPException(
            status_code=403, detail="You can only access your assigned leads"
        )


# ── Context builder ──────────────────────────────────────────────────────────

async def _build_lead_scoring_context(lead: Lead, db: AsyncSession) -> dict:
    """Assemble the context dict for LeadScoringFeature from ORM relationships.

    Pulls from the already-loaded lazy='selectin' relationships to avoid
    extra queries; falls back to empty collections if not available.
    """
    from datetime import date as date_type  # local import to keep top-level clean

    now = datetime.now(timezone.utc)
    # SQLite returns naive datetimes; normalize before subtracting
    created_at = lead.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    days_since_created = (now - created_at).days

    # ── Interaction summary from timeline ────────────────────────────────
    timeline = lead.timeline or []
    interaction_types = ["call", "email", "meeting", "note", "note_added", "status_change"]
    breakdown: dict[str, int] = {}
    last_interaction_date = None
    notes_fragments: list[str] = []

    for entry in sorted(timeline, key=lambda e: e.created_at, reverse=True):
        etype = entry.event_type
        breakdown[etype] = breakdown.get(etype, 0) + 1
        if last_interaction_date is None:
            last_interaction_date = entry.created_at.date().isoformat()
        # Collect note text from metadata (best-effort, first 5)
        if etype in ("note", "note_added") and len(notes_fragments) < 5:
            note_text = entry.event_metadata.get("note") or entry.event_metadata.get("text", "")
            if note_text:
                notes_fragments.append(str(note_text)[:200])

    # ── Appointment summary ──────────────────────────────────────────────
    appointments = lead.appointments or []
    outcomes: list[str] = []
    for appt in appointments:
        outcome = f"{appt.title} ({appt.mode.value if appt.mode else '?'})"
        outcomes.append(outcome)

    return {
        "lead_id": lead.id,
        "status": lead.status.value,
        "source_name": lead.source.name if lead.source else None,
        "days_since_created": days_since_created,
        "assigned_rep_name": lead.assigned_rep.name if lead.assigned_rep else None,
        "interaction_count": len(timeline),
        "interaction_breakdown": breakdown,
        "last_interaction_date": last_interaction_date,
        "interaction_notes_summary": " | ".join(notes_fragments) or None,
        "appointment_count": len(appointments),
        "appointment_outcomes": outcomes[:5],  # Cap at 5 to keep prompt lean
    }


# ── Routes — Lead Scoring ────────────────────────────────────────────────────

@router.post(
    "/{lead_id}/ai/score",
    response_model=LeadScoreRead,
    summary="Run AI lead scoring",
    responses={
        503: {"model": AIUnavailableResponse, "description": "AI service unavailable"},
    },
)
async def score_lead(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ai_client: AIClient = Depends(get_ai_client),
):
    """Run LeadScoringFeature against the lead and persist the result.

    - Assembles context from lead relationships (timeline, appointments).
    - Calls Gemini via AIClient, validates JSON against LeadScoreResult.
    - Persists a new LeadAIInsight row (insight_type='score').
    - Updates denormalized ai_score / ai_score_label / ai_score_updated_at on Lead.
    - Returns the scored result as LeadScoreRead.
    - On AIServiceError → 503 (never 500).
    """
    lead = await _get_lead_or_404(lead_id, db)
    _check_lead_access(lead, current_user)

    # Build context from ORM relationships
    context = await _build_lead_scoring_context(lead, db)

    # Run AI feature
    feature = LeadScoringFeature(client=ai_client)
    try:
        result: LeadScoreResult = await feature.run(context, entity_id=lead_id)
    except AIServiceError as exc:
        logger.warning(
            "AI scoring unavailable for lead_id=%d: %s", lead_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is temporarily unavailable. Please try again later.",
        )

    # Persist insight row
    now = datetime.now(timezone.utc)
    insight = LeadAIInsight(
        lead_id=lead_id,
        insight_type="score",
        payload=result.model_dump(),
        score=float(result.score),
        confidence=None,  # LeadScoreResult doesn't have confidence — kept for future
        model_used=ai_settings.AI_MODEL_NAME,
        generated_at=now,
    )
    db.add(insight)

    # Update denormalized columns on Lead
    lead.ai_score = float(result.score)
    lead.ai_score_label = result.label
    lead.ai_score_updated_at = now

    await db.commit()
    await db.refresh(insight)

    return LeadScoreRead.from_insight(insight)


@router.get(
    "/{lead_id}/ai/score",
    response_model=LeadScoreRead,
    summary="Get latest AI lead score",
    responses={
        404: {"description": "No score insight exists for this lead yet"},
    },
)
async def get_lead_score(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the most recent LeadAIInsight of type 'score' for this lead.

    Returns 404 if no scoring has been run yet.
    """
    lead = await _get_lead_or_404(lead_id, db)
    _check_lead_access(lead, current_user)

    result = await db.execute(
        select(LeadAIInsight)
        .where(
            LeadAIInsight.lead_id == lead_id,
            LeadAIInsight.insight_type == "score",
        )
        .order_by(desc(LeadAIInsight.generated_at))
        .limit(1)
    )
    insight = result.scalar_one_or_none()

    if not insight:
        raise HTTPException(
            status_code=404,
            detail="No AI score found for this lead. Run POST .../ai/score first.",
        )

    return LeadScoreRead.from_insight(insight)


# ── Contact-timing context builder ───────────────────────────────────────────

def _tz_safe(dt) -> "datetime":
    """Return a timezone-aware datetime (UTC). SQLite gives naive datetimes."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _build_contact_timing_context(lead: Lead, db: AsyncSession) -> dict:
    """Extract day-of-week and time-of-day patterns from the lead's history.

    Returns a context dict with:
        interaction_count   int
        interaction_events  list[dict]  — timeline entries with day/time
        appointment_events  list[dict]  — appointment slots (strong signals)
    """
    DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    timeline = lead.timeline or []
    interaction_events: list[dict] = []
    for entry in sorted(timeline, key=lambda e: e.created_at):
        ts = _tz_safe(entry.created_at)
        interaction_events.append({
            "event_type": entry.event_type,
            "day_name": DAYS[ts.weekday()],
            "time_str": ts.strftime("%H:%M"),
            "date_str": ts.date().isoformat(),
        })

    appointments = lead.appointments or []
    appointment_events: list[dict] = []
    for appt in sorted(appointments, key=lambda a: a.start_time):
        ts = _tz_safe(appt.start_time)
        appointment_events.append({
            "title": appt.title,
            "day_name": DAYS[ts.weekday()],
            "time_str": ts.strftime("%H:%M"),
            "date_str": ts.date().isoformat(),
        })

    return {
        "interaction_count": len(timeline),
        "interaction_events": interaction_events,
        "appointment_events": appointment_events,
    }


# ── Routes — Contact Timing ───────────────────────────────────────────────────

@router.post(
    "/{lead_id}/ai/contact-timing",
    response_model=ContactTimingRead,
    summary="Run AI best-contact-time analysis",
    responses={
        503: {"model": AIUnavailableResponse, "description": "AI service unavailable"},
    },
)
async def analyze_contact_timing(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ai_client: AIClient = Depends(get_ai_client),
):
    """Run ContactTimingFeature for a lead and persist the result.

    - If the lead has fewer than AI_MIN_INTERACTIONS interactions, the
      sparse-data guard fires: no Gemini call is made and the response
      contains has_sufficient_data=False with a clear reasoning string.
    - Otherwise calls Gemini with day/time pattern data and returns
      suggested_days, suggested_window, confidence, and reasoning.
    - On AIServiceError → 503 (only possible when data IS sufficient).
    """
    lead = await _get_lead_or_404(lead_id, db)
    _check_lead_access(lead, current_user)

    context = await _build_contact_timing_context(lead, db)

    feature = ContactTimingFeature(client=ai_client)
    try:
        result: ContactTimingResult = await feature.run(context, entity_id=lead_id)
    except AIServiceError as exc:
        logger.warning(
            "AI contact-timing unavailable for lead_id=%d: %s", lead_id, exc
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is temporarily unavailable. Please try again later.",
        )

    # Persist insight — even sparse-data results are stored so the UI
    # knows analysis was attempted and shows the 'not enough history' note.
    now = datetime.now(timezone.utc)
    insight = LeadAIInsight(
        lead_id=lead_id,
        insight_type="contact_timing",
        payload=result.model_dump(),
        score=None,       # Not applicable for contact-timing
        confidence=None,  # Stored in payload as a string label
        model_used=ai_settings.AI_MODEL_NAME,
        generated_at=now,
    )
    db.add(insight)
    await db.commit()
    await db.refresh(insight)

    return ContactTimingRead.from_insight(insight)


@router.get(
    "/{lead_id}/ai/contact-timing",
    response_model=ContactTimingRead,
    summary="Get latest AI contact-timing analysis",
    responses={
        404: {"description": "No contact-timing insight exists for this lead yet"},
    },
)
async def get_lead_contact_timing(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the most recent LeadAIInsight of type 'contact_timing'.

    Returns 404 if contact-timing analysis has never been run for this lead.
    """
    lead = await _get_lead_or_404(lead_id, db)
    _check_lead_access(lead, current_user)

    result = await db.execute(
        select(LeadAIInsight)
        .where(
            LeadAIInsight.lead_id == lead_id,
            LeadAIInsight.insight_type == "contact_timing",
        )
        .order_by(desc(LeadAIInsight.generated_at))
        .limit(1)
    )
    insight = result.scalar_one_or_none()

    if not insight:
        raise HTTPException(
            status_code=404,
            detail="No contact-timing analysis found. Run POST .../ai/contact-timing first.",
        )

    return ContactTimingRead.from_insight(insight)
