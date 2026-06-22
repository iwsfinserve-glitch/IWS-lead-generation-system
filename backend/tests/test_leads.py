"""
test_leads.py — smoke tests for /api/v1/leads/*

Covers:
- GET  /               → list leads (RBAC: sales_rep only sees own)
- POST /               → admin/manager can create, sales_rep cannot
- GET  /{id}           → get single lead
- PATCH /{id}          → update lead; status change creates timeline entry
- DELETE /{id}         → admin only
- GET  /{id}/timeline  → returns timeline entries
- POST /{id}/timeline  → add manual note
"""

import pytest
from tests.conftest import auth_headers


pytestmark = pytest.mark.asyncio


class TestListLeads:
    async def test_admin_sees_all_leads(self, client, admin_token, sample_lead):
        resp = await client.get("/api/v1/leads/", headers=auth_headers(admin_token))
        assert resp.status_code == 200
        leads = resp.json()
        assert isinstance(leads, list)
        assert any(l["id"] == sample_lead.id for l in leads)

    async def test_manager_sees_all_leads(self, client, manager_token, sample_lead):
        resp = await client.get("/api/v1/leads/", headers=auth_headers(manager_token))
        assert resp.status_code == 200

    async def test_sales_rep_only_sees_own_leads(
        self, client, sales_rep_token, sales_rep_user,
        db_session, lead_source
    ):
        """Sales rep should NOT see sample_lead (assigned to admin)."""
        resp = await client.get("/api/v1/leads/", headers=auth_headers(sales_rep_token))
        assert resp.status_code == 200
        leads = resp.json()
        # All returned leads must be assigned to this sales rep
        for lead in leads:
            assert lead["assigned_rep_id"] == sales_rep_user.id

    async def test_unauthenticated_cannot_list(self, client):
        resp = await client.get("/api/v1/leads/")
        assert resp.status_code == 401

    async def test_filter_by_status(self, client, admin_token, sample_lead):
        resp = await client.get(
            "/api/v1/leads/?status=new",
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 200
        for lead in resp.json():
            assert lead["status"] == "new"


class TestCreateLead:
    async def test_admin_can_create_lead(self, client, admin_token, lead_source, admin_user):
        resp = await client.post("/api/v1/leads/", json={
            "name": "New HNI Lead",
            "profession": "Director",
            "email": "hni@example.com",
            "phone_number": "9000000001",
            "source_id": lead_source.id,
            "assigned_rep_id": admin_user.id,
        }, headers=auth_headers(admin_token))
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "New HNI Lead"
        assert body["status"] == "new"   # default status
        assert "id" in body

    async def test_manager_can_create_lead(self, client, manager_token, lead_source, manager_user):
        resp = await client.post("/api/v1/leads/", json={
            "name": "Manager Created Lead",
            "source_id": lead_source.id,
            "assigned_rep_id": manager_user.id,
        }, headers=auth_headers(manager_token))
        assert resp.status_code == 201

    async def test_sales_rep_cannot_create_lead(self, client, sales_rep_token, lead_source, sales_rep_user):
        resp = await client.post("/api/v1/leads/", json={
            "name": "Blocked Lead",
            "source_id": lead_source.id,
            "assigned_rep_id": sales_rep_user.id,
        }, headers=auth_headers(sales_rep_token))
        assert resp.status_code == 403

    async def test_create_lead_missing_required_fields(self, client, admin_token):
        resp = await client.post("/api/v1/leads/", json={},
                                 headers=auth_headers(admin_token))
        assert resp.status_code == 422


class TestGetLead:
    async def test_admin_can_get_lead(self, client, admin_token, sample_lead):
        resp = await client.get(
            f"/api/v1/leads/{sample_lead.id}",
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == sample_lead.id

    async def test_get_nonexistent_lead(self, client, admin_token):
        resp = await client.get("/api/v1/leads/99999", headers=auth_headers(admin_token))
        assert resp.status_code == 404

    async def test_sales_rep_cannot_get_unassigned_lead(
        self, client, sales_rep_token, sample_lead
    ):
        """sample_lead is assigned to admin, not sales_rep."""
        resp = await client.get(
            f"/api/v1/leads/{sample_lead.id}",
            headers=auth_headers(sales_rep_token)
        )
        assert resp.status_code in (403, 404)


class TestUpdateLead:
    async def test_admin_can_update_lead(self, client, admin_token, sample_lead):
        resp = await client.patch(
            f"/api/v1/leads/{sample_lead.id}",
            json={"name": "Updated Lead Name"},
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Lead Name"

    async def test_status_change_is_reflected(self, client, admin_token, sample_lead):
        resp = await client.patch(
            f"/api/v1/leads/{sample_lead.id}",
            json={"status": "in_progress"},
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"

    async def test_update_nonexistent_lead(self, client, admin_token):
        resp = await client.patch(
            "/api/v1/leads/99999",
            json={"name": "Ghost"},
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 404


class TestDeleteLead:
    async def test_admin_can_delete_lead(self, client, admin_token, sample_lead):
        resp = await client.delete(
            f"/api/v1/leads/{sample_lead.id}",
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 204

        # Confirm it's gone
        get_resp = await client.get(
            f"/api/v1/leads/{sample_lead.id}",
            headers=auth_headers(admin_token)
        )
        assert get_resp.status_code == 404

    async def test_sales_rep_cannot_delete_lead(self, client, sales_rep_token, sample_lead):
        resp = await client.delete(
            f"/api/v1/leads/{sample_lead.id}",
            headers=auth_headers(sales_rep_token)
        )
        assert resp.status_code == 403

    async def test_manager_cannot_delete_lead(self, client, manager_token, sample_lead):
        resp = await client.delete(
            f"/api/v1/leads/{sample_lead.id}",
            headers=auth_headers(manager_token)
        )
        assert resp.status_code == 403


class TestLeadTimeline:
    async def test_get_timeline(self, client, admin_token, sample_lead):
        resp = await client.get(
            f"/api/v1/leads/{sample_lead.id}/timeline",
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_add_manual_note_to_timeline(self, client, admin_token, sample_lead):
        resp = await client.post(
            f"/api/v1/leads/{sample_lead.id}/timeline",
            json={
                "event_type": "note",
                "event_metadata": {"note": "Called client, left voicemail."}
            },
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 201

    async def test_status_change_auto_logs_timeline(self, client, admin_token, sample_lead):
        """Changing lead status should automatically inject a timeline entry."""
        await client.patch(
            f"/api/v1/leads/{sample_lead.id}",
            json={"status": "potential"},
            headers=auth_headers(admin_token)
        )
        timeline_resp = await client.get(
            f"/api/v1/leads/{sample_lead.id}/timeline",
            headers=auth_headers(admin_token)
        )
        assert timeline_resp.status_code == 200
        timeline = timeline_resp.json()
        status_events = [e for e in timeline if e["event_type"] == "status_change"]
        assert len(status_events) >= 1
