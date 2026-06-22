"""
test_appointments.py — smoke tests for /api/v1/appointments/*

Google Calendar sync is mocked in conftest.py (autouse fixture),
so no real API calls are made.

Covers:
- GET  /          → list appointments (RBAC filtered)
- POST /          → create appointment + timeline entry
- PATCH /{id}     → update appointment
- DELETE /{id}    → delete appointment
"""

import pytest
from datetime import datetime, timedelta, timezone
from tests.conftest import auth_headers


pytestmark = pytest.mark.asyncio


def future_time(offset_hours: int) -> str:
    """Return an ISO timestamp offset_hours from now."""
    dt = datetime.now(timezone.utc) + timedelta(hours=offset_hours)
    return dt.isoformat()


@pytest.fixture
def appointment_payload(sample_lead, admin_user):
    return {
        "lead_id": sample_lead.id,
        "title": "Initial Consultation",
        "note": "Discuss investment options",
        "mode": "in_person",
        "location": "IWS Office, Panjim",
        "start_time": future_time(24),
        "end_time": future_time(25),
    }


class TestListAppointments:
    async def test_admin_can_list_appointments(self, client, admin_token):
        resp = await client.get("/api/v1/appointments/", headers=auth_headers(admin_token))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_unauthenticated_cannot_list(self, client):
        resp = await client.get("/api/v1/appointments/")
        assert resp.status_code == 401


class TestCreateAppointment:
    async def test_admin_can_create_appointment(
        self, client, admin_token, appointment_payload, sample_lead
    ):
        resp = await client.post(
            "/api/v1/appointments/",
            json=appointment_payload,
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "Initial Consultation"
        assert body["lead_id"] == sample_lead.id
        assert "id" in body

    async def test_sales_rep_cannot_create_appointment_unassigned_lead(
        self, client, sales_rep_token, appointment_payload
    ):
        """Should fail with 403 because appointment_payload uses sample_lead assigned to admin."""
        resp = await client.post(
            "/api/v1/appointments/",
            json=appointment_payload,
            headers=auth_headers(sales_rep_token)
        )
        assert resp.status_code == 403

    async def test_create_appointment_invalid_time(
        self, client, admin_token, appointment_payload
    ):
        """end_time before start_time should be rejected."""
        bad_payload = {**appointment_payload,
                       "start_time": future_time(25),
                       "end_time": future_time(24)}
        resp = await client.post(
            "/api/v1/appointments/",
            json=bad_payload,
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 422

    async def test_create_appointment_missing_fields(self, client, admin_token):
        resp = await client.post(
            "/api/v1/appointments/",
            json={},
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 422


class TestUpdateAppointment:
    async def test_update_appointment_title(
        self, client, admin_token, appointment_payload
    ):
        # First create one
        create_resp = await client.post(
            "/api/v1/appointments/",
            json=appointment_payload,
            headers=auth_headers(admin_token)
        )
        assert create_resp.status_code == 201
        appt_id = create_resp.json()["id"]

        # Then update it
        resp = await client.patch(
            f"/api/v1/appointments/{appt_id}",
            json={"title": "Follow-up Meeting"},
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Follow-up Meeting"

    async def test_update_nonexistent_appointment(self, client, admin_token):
        resp = await client.patch(
            "/api/v1/appointments/99999",
            json={"title": "Ghost"},
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 404


class TestDeleteAppointment:
    async def test_admin_can_delete_appointment(
        self, client, admin_token, appointment_payload
    ):
        create_resp = await client.post(
            "/api/v1/appointments/",
            json=appointment_payload,
            headers=auth_headers(admin_token)
        )
        assert create_resp.status_code == 201
        appt_id = create_resp.json()["id"]

        resp = await client.delete(
            f"/api/v1/appointments/{appt_id}",
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 204

    async def test_delete_nonexistent_appointment(self, client, admin_token):
        resp = await client.delete(
            "/api/v1/appointments/99999",
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 404
