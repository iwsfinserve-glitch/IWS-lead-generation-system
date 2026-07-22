"""
test_leads.py — smoke tests for /api/v1/leads/*

Covers:
- GET  /               → list leads (RBAC: sales_rep only sees own)
- POST /               → admin/manager/sales_rep can create
- GET  /{id}           → get single lead
- PATCH /{id}          → update lead; status change creates timeline entry
- DELETE /{id}         → admin only
- GET  /{id}/timeline  → returns timeline entries
- POST /{id}/timeline  → add manual note
- POST /public/web-lead → SEO intake endpoint (API key auth)
- PATCH /{id}/claim     → atomic claiming with race condition protection
"""

import pytest
from app.models.lead import Lead
from app.models.enums import LeadStatus
from tests.conftest import auth_headers


pytestmark = pytest.mark.asyncio

# ── Helpers ──────────────────────────────────────────────────────────

SEO_API_KEY = "test_seo_key_for_tests_only"


def seo_headers() -> dict:
    return {"X-API-Key": SEO_API_KEY}


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
            "/api/v1/leads/?status=unassigned",
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 200
        for lead in resp.json():
            assert lead["status"] == "unassigned"


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
        assert body["status"] == "in_progress"
        assert "id" in body

    async def test_admin_can_create_lead_with_note(self, client, admin_token, lead_source, admin_user):
        resp = await client.post("/api/v1/leads/", json={
            "name": "Lead With Note",
            "profession": "Doctor",
            "email": "doctor@example.com",
            "phone_number": "9000000002",
            "source_id": lead_source.id,
            "assigned_rep_id": admin_user.id,
            "note": "Initial discussion went great, looking for aggressive growth."
        }, headers=auth_headers(admin_token))
        assert resp.status_code == 201
        body = resp.json()
        lead_id = body["id"]

        timeline_resp = await client.get(f"/api/v1/leads/{lead_id}/timeline", headers=auth_headers(admin_token))
        assert timeline_resp.status_code == 200
        timeline = timeline_resp.json()

        # Check that note is logged in both lead_created and separate note event
        created_event = next(e for e in timeline if e["event_type"] == "lead_created")
        assert created_event["event_metadata"]["note"] == "Initial discussion went great, looking for aggressive growth."

        note_events = [e for e in timeline if e["event_type"] == "note"]
        assert any(e["event_metadata"]["note"] == "Initial discussion went great, looking for aggressive growth." for e in note_events)

    async def test_manager_can_create_lead(self, client, manager_token, lead_source, manager_user):
        resp = await client.post("/api/v1/leads/", json={
            "name": "Manager Created Lead",
            "profession": "Consultant",
            "email": "consultant@example.com",
            "phone_number": "9000000003",
            "source_id": lead_source.id,
            "assigned_rep_id": manager_user.id,
        }, headers=auth_headers(manager_token))
        assert resp.status_code == 201

    async def test_sales_rep_can_create_own_lead(self, client, sales_rep_token, lead_source, sales_rep_user):
        resp = await client.post("/api/v1/leads/", json={
            "name": "Sales Rep Created Lead",
            "profession": "Engineer",
            "email": "engineer@example.com",
            "phone_number": "9000000004",
            "source_id": lead_source.id,
            "assigned_rep_id": sales_rep_user.id,
        }, headers=auth_headers(sales_rep_token))
        assert resp.status_code == 201
        assert resp.json()["assigned_rep_id"] == sales_rep_user.id
        assert resp.json()["status"] == "in_progress"

    async def test_sales_rep_cannot_assign_lead_to_others(self, client, sales_rep_token, lead_source, admin_user):
        resp = await client.post("/api/v1/leads/", json={
            "name": "Unauthorized Assignment Lead",
            "profession": "Architect",
            "email": "architect@example.com",
            "phone_number": "9000000005",
            "source_id": lead_source.id,
            "assigned_rep_id": admin_user.id,
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

    async def test_sales_rep_can_get_unassigned_lead(
        self, client, sales_rep_token, sample_lead
    ):
        """Sales rep can view details of an unassigned lead."""
        resp = await client.get(
            f"/api/v1/leads/{sample_lead.id}",
            headers=auth_headers(sales_rep_token)
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == sample_lead.id

    async def test_sales_rep_can_get_other_rep_lead_details(
        self, client, sales_rep_token, db_session, lead_source, admin_user
    ):
        """Sales rep CAN view details of a lead assigned to another user (read-only access)."""
        lead = Lead(
            name="Other Rep Lead",
            profession="Executive",
            email="other@example.com",
            phone_number="9876543211",
            status=LeadStatus.in_progress,
            source_id=lead_source.id,
            assigned_rep_id=admin_user.id,
        )
        db_session.add(lead)
        await db_session.commit()
        await db_session.refresh(lead)

        resp = await client.get(
            f"/api/v1/leads/{lead.id}",
            headers=auth_headers(sales_rep_token)
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == lead.id


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

    async def test_sales_rep_cannot_update_other_rep_lead(
        self, client, sales_rep_token, db_session, lead_source, admin_user
    ):
        """Sales rep CANNOT update a lead assigned to another user."""
        lead = Lead(
            name="Other Rep Lead To Update",
            profession="Executive",
            email="otherup@example.com",
            phone_number="9876543212",
            status=LeadStatus.in_progress,
            source_id=lead_source.id,
            assigned_rep_id=admin_user.id,
        )
        db_session.add(lead)
        await db_session.commit()
        await db_session.refresh(lead)

        resp = await client.patch(
            f"/api/v1/leads/{lead.id}",
            json={"profession": "Hacked Profession"},
            headers=auth_headers(sales_rep_token)
        )
        assert resp.status_code == 403

    async def test_manager_assignment_auto_transitions_unassigned_to_in_progress(
        self, client, admin_token, sales_rep_user, lead_source, db_session
    ):
        """Assigning a rep to an unassigned lead should auto-set status to in_progress."""
        from app.models.lead import Lead
        from app.models.enums import LeadStatus
        unassigned_lead = Lead(
            name="Auto Transition Lead",
            status=LeadStatus.unassigned,
            source_id=lead_source.id,
            assigned_rep_id=None,
        )
        db_session.add(unassigned_lead)
        await db_session.commit()
        await db_session.refresh(unassigned_lead)

        resp = await client.patch(
            f"/api/v1/leads/{unassigned_lead.id}",
            json={"assigned_rep_id": sales_rep_user.id},
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "in_progress"
        assert body["assigned_rep_id"] == sales_rep_user.id

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

    async def test_sales_rep_cannot_add_note_to_other_rep_lead(
        self, client, sales_rep_token, db_session, lead_source, admin_user
    ):
        """Sales rep CANNOT add notes to a lead assigned to another user."""
        lead = Lead(
            name="Other Rep Lead For Note",
            profession="Executive",
            email="othernote@example.com",
            phone_number="9876543213",
            status=LeadStatus.in_progress,
            source_id=lead_source.id,
            assigned_rep_id=admin_user.id,
        )
        db_session.add(lead)
        await db_session.commit()
        await db_session.refresh(lead)

        resp = await client.post(
            f"/api/v1/leads/{lead.id}/timeline",
            json={"event_type": "note", "event_metadata": {"note": "Unauthorized note"}},
            headers=auth_headers(sales_rep_token)
        )
        assert resp.status_code == 403

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


class TestPublicWebLead:
    """Tests for POST /api/v1/leads/public/web-lead (SEO intake endpoint)."""

    @staticmethod
    def _seo_key() -> str:
        """Read the configured SEO API key from app settings (loaded from .env)."""
        from app.core.config import settings
        return settings.SEO_WEB_API_KEY

    async def test_valid_seo_submission_creates_unassigned_lead(self, client):
        resp = await client.post(
            "/api/v1/leads/public/web-lead",
            json={
                "name": "Priya Sharma",
                "email": "priya@example.com",
                "phone_number": "9123456789",
                "profession": "Business Owner",
                "message": "I am interested in your investment opportunities.",
            },
            headers={"X-API-Key": self._seo_key()},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "unassigned"
        assert body["assigned_rep_id"] is None
        assert body["source_name"] == "SEO"

    async def test_seo_submission_stores_message_as_timeline_note(self, client, admin_token):
        resp = await client.post(
            "/api/v1/leads/public/web-lead",
            json={
                "name": "Rahul Verma",
                "email": "rahul@example.com",
                "phone_number": "9123456788",
                "profession": "Architect",
                "message": "Looking to invest 50L in real estate.",
            },
            headers={"X-API-Key": self._seo_key()},
        )
        assert resp.status_code == 201
        lead_id = resp.json()["id"]

        timeline_resp = await client.get(
            f"/api/v1/leads/{lead_id}/timeline",
            headers=auth_headers(admin_token),
        )
        assert timeline_resp.status_code == 200
        timeline = timeline_resp.json()
        note_events = [e for e in timeline if e["event_type"] == "note"]
        assert any(
            "50L in real estate" in e["event_metadata"].get("note", "")
            for e in note_events
        )

    async def test_invalid_api_key_rejected(self, client):
        resp = await client.post(
            "/api/v1/leads/public/web-lead",
            json={
                "name": "Hacker",
                "email": "hacker@example.com",
                "phone_number": "0000000000",
                "profession": "Hacker",
            },
            headers={"X-API-Key": "wrong_key_definitely_not_valid"},
        )
        assert resp.status_code == 403

    async def test_missing_api_key_rejected(self, client):
        resp = await client.post(
            "/api/v1/leads/public/web-lead",
            json={
                "name": "No Key Lead",
                "email": "nokey@example.com",
                "phone_number": "0000000000",
                "profession": "Developer",
            },
        )
        # FastAPI returns 422 for missing required header
        assert resp.status_code in (403, 422)

    async def test_seo_lead_missing_name_rejected(self, client):
        resp = await client.post(
            "/api/v1/leads/public/web-lead",
            json={
                "email": "noname@example.com",
                "phone_number": "0000000000",
                "profession": "Tester",
            },
            headers={"X-API-Key": self._seo_key()},
        )
        assert resp.status_code == 422


class TestAtomicClaimLead:
    """Tests for PATCH /api/v1/leads/{id}/claim — atomic lead claiming."""

    async def _create_unassigned_lead(self, db_session, lead_source) -> "Lead":
        """Helper: create a fresh unassigned lead for claiming tests."""
        from app.models.lead import Lead
        from app.models.enums import LeadStatus
        lead = Lead(
            name="Unassigned Claim Target",
            status=LeadStatus.unassigned,
            source_id=lead_source.id,
            assigned_rep_id=None,
        )
        db_session.add(lead)
        await db_session.commit()
        await db_session.refresh(lead)
        return lead

    async def test_sales_rep_can_claim_unassigned_lead(
        self, client, sales_rep_token, sales_rep_user, lead_source, db_session
    ):
        lead = await self._create_unassigned_lead(db_session, lead_source)

        resp = await client.patch(
            f"/api/v1/leads/{lead.id}/claim",
            headers=auth_headers(sales_rep_token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "in_progress"
        assert body["assigned_rep_id"] == sales_rep_user.id

    async def test_claim_logs_timeline_entries(
        self, client, sales_rep_token, admin_token, lead_source, db_session
    ):
        lead = await self._create_unassigned_lead(db_session, lead_source)

        await client.patch(
            f"/api/v1/leads/{lead.id}/claim",
            headers=auth_headers(sales_rep_token),
        )

        timeline_resp = await client.get(
            f"/api/v1/leads/{lead.id}/timeline",
            headers=auth_headers(admin_token),
        )
        assert timeline_resp.status_code == 200
        timeline = timeline_resp.json()
        assert any(e["event_type"] == "lead_assigned" for e in timeline)
        assert any(e["event_type"] == "status_change" for e in timeline)

    async def test_race_condition_second_claim_returns_409(
        self, client, sales_rep_token, manager_token, lead_source, db_session
    ):
        """Simulates race condition: first claim succeeds, second gets 409 Conflict."""
        lead = await self._create_unassigned_lead(db_session, lead_source)

        # First claim — should succeed
        resp1 = await client.patch(
            f"/api/v1/leads/{lead.id}/claim",
            headers=auth_headers(sales_rep_token),
        )
        assert resp1.status_code == 200

        # Second claim on the same lead — should get 409
        resp2 = await client.patch(
            f"/api/v1/leads/{lead.id}/claim",
            headers=auth_headers(manager_token),
        )
        assert resp2.status_code == 409
        assert "already been claimed" in resp2.json()["detail"].lower()

    async def test_claim_nonexistent_lead_returns_404(self, client, sales_rep_token):
        resp = await client.patch(
            "/api/v1/leads/99999/claim",
            headers=auth_headers(sales_rep_token),
        )
        assert resp.status_code == 404

    async def test_admin_cannot_claim_lead(self, client, admin_token, lead_source, db_session):
        """Admins are excluded from claim endpoint (only sales_rep and manager allowed)."""
        lead = await self._create_unassigned_lead(db_session, lead_source)
        resp = await client.patch(
            f"/api/v1/leads/{lead.id}/claim",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 403
