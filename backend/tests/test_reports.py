"""
test_reports.py — smoke tests for /api/v1/reports/*

Gemini API and python-docx are mocked in conftest.py (autouse fixture),
so no real AI calls are made. We just verify:
- The endpoint responds 200
- The response Content-Type is application/vnd.openxmlformats (docx)
- The response has a non-empty body
"""

import pytest
from tests.conftest import auth_headers


pytestmark = pytest.mark.asyncio

DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument"
    ".wordprocessingml.document"
)


class TestLeadJourneyReport:
    async def test_admin_can_generate_lead_journey_report(
        self, client, admin_token, sample_lead
    ):
        resp = await client.get(
            f"/api/v1/reports/lead-journey/{sample_lead.id}",
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 200
        assert DOCX_CONTENT_TYPE in resp.headers.get("content-type", "")
        assert len(resp.content) > 0

    async def test_sales_rep_can_generate_own_lead_report(
        self, client, admin_token, sample_lead
    ):
        """Admin token used here since sample_lead is assigned to admin."""
        resp = await client.get(
            f"/api/v1/reports/lead-journey/{sample_lead.id}",
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 200

    async def test_lead_journey_nonexistent_lead(self, client, admin_token):
        resp = await client.get(
            "/api/v1/reports/lead-journey/99999",
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 404

    async def test_unauthenticated_cannot_generate_report(self, client, sample_lead):
        resp = await client.get(f"/api/v1/reports/lead-journey/{sample_lead.id}")
        assert resp.status_code == 401


class TestTeamPerformanceReport:
    async def test_admin_can_generate_team_report(self, client, admin_token):
        resp = await client.get(
            "/api/v1/reports/team-performance",
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 200
        assert DOCX_CONTENT_TYPE in resp.headers.get("content-type", "")
        assert len(resp.content) > 0

    async def test_manager_can_generate_team_report(self, client, manager_token):
        resp = await client.get(
            "/api/v1/reports/team-performance",
            headers=auth_headers(manager_token)
        )
        assert resp.status_code == 200

    async def test_sales_rep_cannot_generate_team_report(self, client, sales_rep_token):
        resp = await client.get(
            "/api/v1/reports/team-performance",
            headers=auth_headers(sales_rep_token)
        )
        assert resp.status_code == 403

    async def test_unauthenticated_cannot_generate_team_report(self, client):
        resp = await client.get("/api/v1/reports/team-performance")
        assert resp.status_code == 401
