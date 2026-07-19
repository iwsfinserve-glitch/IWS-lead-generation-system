# backend/tests/test_ai_insights.py
"""
test_ai_insights.py — tests for:
    POST /api/v1/leads/{id}/ai/score
    GET  /api/v1/leads/{id}/ai/score
    POST /api/v1/leads/{id}/ai/contact-timing
    GET  /api/v1/leads/{id}/ai/contact-timing

All AI calls are mocked at the feature level — no real Gemini calls are made.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import auth_headers
from app.ai.features.lead_scoring import LeadScoreResult
from app.ai.features.contact_timing import ContactTimingResult
from app.ai.exceptions import AIServiceError

pytestmark = pytest.mark.asyncio

# ─────────────────────────────────────────────────────────────────────────────
# Shared mock results
# ─────────────────────────────────────────────────────────────────────────────

MOCK_SCORE_RESULT = LeadScoreResult(
    score=75,
    label="warm",
    reasoning="Two calls in the past week indicate active interest.",
    key_signals=["Status: in_progress", "Two recent calls", "Appointment booked"],
    suggested_next_action="Schedule a product demo within 3 days.",
)

MOCK_TIMING_SUFFICIENT = ContactTimingResult(
    has_sufficient_data=True,
    suggested_days=["Tuesday", "Thursday"],
    suggested_window="10:00-12:00",
    confidence="medium",
    reasoning="Three of five interactions occurred Tuesday mornings.",
)

MOCK_TIMING_SPARSE = ContactTimingResult(
    has_sufficient_data=False,
    suggested_days=[],
    suggested_window=None,
    confidence="low",
    reasoning="Not enough interaction history yet — 1 interaction(s) recorded, minimum 3 required.",
)

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def mock_lead_scoring():
    with patch(
        "app.api.v1.ai_insights.LeadScoringFeature.run",
        new_callable=AsyncMock,
        return_value=MOCK_SCORE_RESULT,
    ) as m:
        yield m


@pytest.fixture()
def mock_lead_scoring_fail():
    with patch(
        "app.api.v1.ai_insights.LeadScoringFeature.run",
        new_callable=AsyncMock,
        side_effect=AIServiceError("Gemini unavailable"),
    ) as m:
        yield m


@pytest.fixture()
def mock_contact_timing_sufficient():
    with patch(
        "app.api.v1.ai_insights.ContactTimingFeature.run",
        new_callable=AsyncMock,
        return_value=MOCK_TIMING_SUFFICIENT,
    ) as m:
        yield m


@pytest.fixture()
def mock_contact_timing_sparse():
    with patch(
        "app.api.v1.ai_insights.ContactTimingFeature.run",
        new_callable=AsyncMock,
        return_value=MOCK_TIMING_SPARSE,
    ) as m:
        yield m


@pytest.fixture()
def mock_contact_timing_fail():
    with patch(
        "app.api.v1.ai_insights.ContactTimingFeature.run",
        new_callable=AsyncMock,
        side_effect=AIServiceError("Gemini unavailable"),
    ) as m:
        yield m


# ─────────────────────────────────────────────────────────────────────────────
# Lead Scoring — POST
# ─────────────────────────────────────────────────────────────────────────────

class TestPostLeadScore:
    async def test_admin_can_score_lead(
        self, client, admin_token, sample_lead, mock_lead_scoring
    ):
        resp = await client.post(
            f"/api/v1/leads/{sample_lead.id}/ai/score",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["score"] == 75
        assert data["label"] == "warm"
        assert "reasoning" in data
        assert "key_signals" in data
        assert "suggested_next_action" in data
        assert "generated_at" in data
        assert "model_used" in data

    async def test_post_score_updates_denorm_fields(
        self, client, admin_token, sample_lead, db_session, mock_lead_scoring
    ):
        from sqlalchemy import select
        from app.models.lead import Lead

        await client.post(
            f"/api/v1/leads/{sample_lead.id}/ai/score",
            headers=auth_headers(admin_token),
        )
        result = await db_session.execute(
            select(Lead).where(Lead.id == sample_lead.id)
        )
        lead = result.scalar_one()
        assert lead.ai_score == 75.0
        assert lead.ai_score_label == "warm"
        assert lead.ai_score_updated_at is not None

    async def test_score_returns_503_on_ai_error(
        self, client, admin_token, sample_lead, mock_lead_scoring_fail
    ):
        resp = await client.post(
            f"/api/v1/leads/{sample_lead.id}/ai/score",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 503
        assert "unavailable" in resp.json()["detail"].lower()

    async def test_score_nonexistent_lead_returns_404(
        self, client, admin_token, mock_lead_scoring
    ):
        resp = await client.post(
            "/api/v1/leads/99999/ai/score",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 404

    async def test_unauthenticated_cannot_score(self, client, sample_lead):
        resp = await client.post(f"/api/v1/leads/{sample_lead.id}/ai/score")
        assert resp.status_code == 401

    async def test_sales_rep_cannot_score_another_reps_lead(
        self, client, db_session, sales_rep_token, lead_source, manager_user
    ):
        from app.models.lead import Lead
        from app.models.enums import LeadStatus

        other_lead = Lead(
            name="Other Lead",
            status=LeadStatus.new,
            source_id=lead_source.id,
            assigned_rep_id=manager_user.id,
        )
        db_session.add(other_lead)
        await db_session.commit()
        await db_session.refresh(other_lead)

        with patch(
            "app.api.v1.ai_insights.LeadScoringFeature.run",
            new_callable=AsyncMock,
            return_value=MOCK_SCORE_RESULT,
        ):
            resp = await client.post(
                f"/api/v1/leads/{other_lead.id}/ai/score",
                headers=auth_headers(sales_rep_token),
            )
        assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# Lead Scoring — GET
# ─────────────────────────────────────────────────────────────────────────────

class TestGetLeadScore:
    async def test_get_score_returns_404_when_no_insight(
        self, client, admin_token, sample_lead
    ):
        resp = await client.get(
            f"/api/v1/leads/{sample_lead.id}/ai/score",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 404

    async def test_get_score_returns_latest_after_post(
        self, client, admin_token, sample_lead, mock_lead_scoring
    ):
        post_resp = await client.post(
            f"/api/v1/leads/{sample_lead.id}/ai/score",
            headers=auth_headers(admin_token),
        )
        assert post_resp.status_code == 200

        get_resp = await client.get(
            f"/api/v1/leads/{sample_lead.id}/ai/score",
            headers=auth_headers(admin_token),
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["score"] == 75
        assert data["label"] == "warm"

    async def test_get_score_nonexistent_lead_returns_404(
        self, client, admin_token
    ):
        resp = await client.get(
            "/api/v1/leads/99999/ai/score",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 404

    async def test_unauthenticated_cannot_get_score(self, client, sample_lead):
        resp = await client.get(f"/api/v1/leads/{sample_lead.id}/ai/score")
        assert resp.status_code == 401

    async def test_lead_list_includes_ai_fields_after_scoring(
        self, client, admin_token, sample_lead, mock_lead_scoring
    ):
        await client.post(
            f"/api/v1/leads/{sample_lead.id}/ai/score",
            headers=auth_headers(admin_token),
        )
        leads_resp = await client.get("/api/v1/leads/", headers=auth_headers(admin_token))
        assert leads_resp.status_code == 200
        scored = next((l for l in leads_resp.json() if l["id"] == sample_lead.id), None)
        assert scored is not None
        assert scored["ai_score"] == 75.0
        assert scored["ai_score_label"] == "warm"


# ─────────────────────────────────────────────────────────────────────────────
# Contact Timing — POST
# ─────────────────────────────────────────────────────────────────────────────

class TestPostContactTiming:
    async def test_post_returns_200_with_sufficient_data(
        self, client, admin_token, sample_lead, mock_contact_timing_sufficient
    ):
        resp = await client.post(
            f"/api/v1/leads/{sample_lead.id}/ai/contact-timing",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["has_sufficient_data"] is True
        assert data["suggested_days"] == ["Tuesday", "Thursday"]
        assert data["suggested_window"] == "10:00-12:00"
        assert data["confidence"] == "medium"
        assert "reasoning" in data
        assert "generated_at" in data
        assert "model_used" in data

    async def test_post_returns_sparse_flag_when_not_enough_data(
        self, client, admin_token, sample_lead, mock_contact_timing_sparse
    ):
        """Sparse-data guard result: 200 OK but has_sufficient_data=False."""
        resp = await client.post(
            f"/api/v1/leads/{sample_lead.id}/ai/contact-timing",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["has_sufficient_data"] is False
        assert data["suggested_window"] is None
        assert data["suggested_days"] == []
        assert "not enough" in data["reasoning"].lower()

    async def test_post_returns_503_on_ai_error(
        self, client, admin_token, sample_lead, mock_contact_timing_fail
    ):
        resp = await client.post(
            f"/api/v1/leads/{sample_lead.id}/ai/contact-timing",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 503
        assert "unavailable" in resp.json()["detail"].lower()

    async def test_post_nonexistent_lead_returns_404(
        self, client, admin_token, mock_contact_timing_sufficient
    ):
        resp = await client.post(
            "/api/v1/leads/99999/ai/contact-timing",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 404

    async def test_unauthenticated_cannot_analyze(self, client, sample_lead):
        resp = await client.post(
            f"/api/v1/leads/{sample_lead.id}/ai/contact-timing"
        )
        assert resp.status_code == 401

    async def test_sparse_result_is_persisted_and_retrievable(
        self, client, admin_token, sample_lead, mock_contact_timing_sparse
    ):
        """Even a has_sufficient_data=False result is stored — GET shows the note."""
        post_resp = await client.post(
            f"/api/v1/leads/{sample_lead.id}/ai/contact-timing",
            headers=auth_headers(admin_token),
        )
        assert post_resp.status_code == 200

        get_resp = await client.get(
            f"/api/v1/leads/{sample_lead.id}/ai/contact-timing",
            headers=auth_headers(admin_token),
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["has_sufficient_data"] is False


# ─────────────────────────────────────────────────────────────────────────────
# Contact Timing — GET
# ─────────────────────────────────────────────────────────────────────────────

class TestGetContactTiming:
    async def test_get_returns_404_when_no_insight(
        self, client, admin_token, sample_lead
    ):
        resp = await client.get(
            f"/api/v1/leads/{sample_lead.id}/ai/contact-timing",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 404

    async def test_get_returns_latest_after_post(
        self, client, admin_token, sample_lead, mock_contact_timing_sufficient
    ):
        post_resp = await client.post(
            f"/api/v1/leads/{sample_lead.id}/ai/contact-timing",
            headers=auth_headers(admin_token),
        )
        assert post_resp.status_code == 200

        get_resp = await client.get(
            f"/api/v1/leads/{sample_lead.id}/ai/contact-timing",
            headers=auth_headers(admin_token),
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["suggested_days"] == ["Tuesday", "Thursday"]
        assert data["suggested_window"] == "10:00-12:00"

    async def test_get_nonexistent_lead_returns_404(self, client, admin_token):
        resp = await client.get(
            "/api/v1/leads/99999/ai/contact-timing",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 404

    async def test_unauthenticated_cannot_get(self, client, sample_lead):
        resp = await client.get(
            f"/api/v1/leads/{sample_lead.id}/ai/contact-timing"
        )
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — sparse-data guard logic inside ContactTimingFeature directly
# ─────────────────────────────────────────────────────────────────────────────

class TestContactTimingSparseGuardUnit:
    async def test_guard_fires_when_below_threshold(self):
        """run() returns sparse result without ever touching AIClient."""
        from app.ai.features.contact_timing import ContactTimingFeature

        mock_client = MagicMock()
        feature = ContactTimingFeature(client=mock_client)

        result = await feature.run(
            {"interaction_count": 1, "interaction_events": [], "appointment_events": []},
            entity_id=999,
        )

        assert result.has_sufficient_data is False
        assert result.suggested_window is None
        assert result.suggested_days == []
        mock_client.generate.assert_not_called()

    async def test_guard_does_not_fire_at_threshold(self):
        """When count == AI_MIN_INTERACTIONS, the feature calls client.generate."""
        from app.ai.features.contact_timing import ContactTimingFeature

        sufficient_result = ContactTimingResult(
            has_sufficient_data=True,
            suggested_days=["Monday"],
            suggested_window="09:00-11:00",
            confidence="low",
            reasoning="Barely enough data.",
        )
        mock_client = MagicMock()
        mock_client.generate = AsyncMock(return_value=sufficient_result)

        feature = ContactTimingFeature(client=mock_client)
        context = {
            "interaction_count": 3,  # exactly at default AI_MIN_INTERACTIONS
            "interaction_events": [
                {"event_type": "note_added", "day_name": "Monday",
                 "time_str": "09:30", "date_str": "2026-07-01"},
            ] * 3,
            "appointment_events": [],
        }

        result = await feature.run(context, entity_id=42)

        mock_client.generate.assert_called_once()
        assert result.has_sufficient_data is True
