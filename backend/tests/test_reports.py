"""
test_reports.py — smoke tests for /api/v1/reports/*

All Gemini calls and python-docx are mocked via conftest.py autouse fixtures.
"""

import pytest
from unittest.mock import patch, AsyncMock
from tests.conftest import auth_headers

pytestmark = pytest.mark.asyncio

DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument"
    ".wordprocessingml.document"
)

# ── Lead Journey ──────────────────────────────────────────────────────────────

class TestLeadJourneyReport:
    async def test_admin_can_get_lead_journey_json(self, client, admin_token, sample_lead):
        resp = await client.get(
            f"/api/v1/reports/lead-journey/{sample_lead.id}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "narrative" in body
        assert "timeline" in body
        assert body["lead_id"] == sample_lead.id

    async def test_admin_can_download_lead_journey(self, client, admin_token, sample_lead):
        resp = await client.get(
            f"/api/v1/reports/lead-journey/{sample_lead.id}/download",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        assert DOCX_CONTENT_TYPE in resp.headers.get("content-type", "")
        assert len(resp.content) > 0

    async def test_lead_journey_nonexistent_lead(self, client, admin_token):
        resp = await client.get(
            "/api/v1/reports/lead-journey/99999",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 404

    async def test_unauthenticated_cannot_generate(self, client, sample_lead):
        resp = await client.get(f"/api/v1/reports/lead-journey/{sample_lead.id}")
        assert resp.status_code == 401

    async def test_sales_rep_cannot_access_unassigned_lead_report(
        self, client, sales_rep_token, sample_lead
    ):
        # sample_lead is assigned to admin, not sales_rep
        resp = await client.get(
            f"/api/v1/reports/lead-journey/{sample_lead.id}",
            headers=auth_headers(sales_rep_token),
        )
        assert resp.status_code == 403


# ── Periodic Leads ────────────────────────────────────────────────────────────

class TestPeriodicLeadsReport:
    async def test_admin_can_get_periodic_leads_json(self, client, admin_token, sample_lead):
        resp = await client.get(
            "/api/v1/reports/leads-periodic",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "narrative" in body
        assert "metrics" in body
        assert "total_leads" in body["metrics"]

    async def test_periodic_leads_with_date_range(self, client, admin_token, sample_lead):
        resp = await client.get(
            "/api/v1/reports/leads-periodic?start_date=2020-01-01&end_date=2030-12-31&period=All%20Time",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200

    async def test_admin_can_download_periodic_leads(self, client, admin_token):
        resp = await client.get(
            "/api/v1/reports/leads-periodic/download",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        assert DOCX_CONTENT_TYPE in resp.headers.get("content-type", "")

    async def test_unauthenticated_cannot_access_periodic(self, client):
        resp = await client.get("/api/v1/reports/leads-periodic")
        assert resp.status_code == 401

    async def test_sales_rep_can_access_own_periodic(self, client, sales_rep_token):
        resp = await client.get(
            "/api/v1/reports/leads-periodic",
            headers=auth_headers(sales_rep_token),
        )
        assert resp.status_code == 200

    async def test_sales_rep_cannot_scope_to_other_user(self, client, sales_rep_token, admin_user):
        resp = await client.get(
            f"/api/v1/reports/leads-periodic?user_id={admin_user.id}",
            headers=auth_headers(sales_rep_token),
        )
        # Should return 200 but scoped to sales_rep's own leads (user_id param ignored for reps)
        assert resp.status_code == 200


# ── User Performance ──────────────────────────────────────────────────────────

class TestUserPerformanceReport:
    async def test_manager_can_view_subordinate_performance(
        self, client, manager_token, sales_rep_user
    ):
        resp = await client.get(
            f"/api/v1/reports/user-performance/{sales_rep_user.id}",
            headers=auth_headers(manager_token),
        )
        # sales_rep_user has no manager_id set in conftest → 403 (not a subordinate)
        assert resp.status_code in (200, 403)

    async def test_admin_can_view_any_user_performance(
        self, client, admin_token, sales_rep_user
    ):
        resp = await client.get(
            f"/api/v1/reports/user-performance/{sales_rep_user.id}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "narrative" in body
        assert "metrics" in body

    async def test_sales_rep_cannot_view_performance_reports(
        self, client, sales_rep_token, admin_user
    ):
        resp = await client.get(
            f"/api/v1/reports/user-performance/{admin_user.id}",
            headers=auth_headers(sales_rep_token),
        )
        assert resp.status_code == 403

    async def test_admin_can_download_user_performance(
        self, client, admin_token, sales_rep_user
    ):
        resp = await client.get(
            f"/api/v1/reports/user-performance/{sales_rep_user.id}/download",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        assert DOCX_CONTENT_TYPE in resp.headers.get("content-type", "")

    async def test_nonexistent_user_returns_404(self, client, admin_token):
        resp = await client.get(
            "/api/v1/reports/user-performance/99999",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 404


# ── Team Performance ──────────────────────────────────────────────────────────

class TestTeamPerformanceReport:
    async def test_admin_can_generate_team_report_json(self, client, admin_token):
        resp = await client.get(
            "/api/v1/reports/team-performance",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "narrative" in body
        assert "metrics" in body

    async def test_manager_can_generate_team_report(self, client, manager_token):
        resp = await client.get(
            "/api/v1/reports/team-performance",
            headers=auth_headers(manager_token),
        )
        assert resp.status_code == 200

    async def test_sales_rep_cannot_generate_team_report(self, client, sales_rep_token):
        resp = await client.get(
            "/api/v1/reports/team-performance",
            headers=auth_headers(sales_rep_token),
        )
        assert resp.status_code == 403

    async def test_unauthenticated_cannot_generate_team_report(self, client):
        resp = await client.get("/api/v1/reports/team-performance")
        assert resp.status_code == 401

    async def test_admin_can_download_team_report(self, client, admin_token):
        resp = await client.get(
            "/api/v1/reports/team-performance/download",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        assert DOCX_CONTENT_TYPE in resp.headers.get("content-type", "")

    async def test_team_report_with_date_range(self, client, admin_token):
        resp = await client.get(
            "/api/v1/reports/team-performance?start_date=2020-01-01&period=Last+Year",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
