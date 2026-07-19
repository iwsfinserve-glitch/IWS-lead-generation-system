"""
Tests for Lead Transfer Requests endpoints (/api/v1/lead-transfer-requests/*).
"""

import pytest
from tests.conftest import auth_headers


class TestLeadTransfers:
    @pytest.mark.asyncio
    async def test_request_lead_transfer(
        self, client, admin_token, sales_rep_user, sample_lead
    ):
        """Assigned rep (admin in sample_lead) can request transferring a lead."""
        payload = {
            "lead_id": sample_lead.id,
            "to_user_id": sales_rep_user.id,
            "reason": "Client requested transfer to another rep",
        }
        resp = await client.post(
            "/api/v1/lead-transfer-requests/",
            json=payload,
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["lead_id"] == sample_lead.id
        assert data["to_user_id"] == sales_rep_user.id
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_list_lead_transfer_requests(self, client, manager_token):
        """Manager/admin can list pending lead transfer requests."""
        resp = await client.get(
            "/api/v1/lead-transfer-requests/",
            headers=auth_headers(manager_token),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_approve_lead_transfer(
        self, client, admin_token, manager_token, sales_rep_user, sample_lead
    ):
        """Manager can approve a pending transfer request."""
        # First request the transfer as the assigned rep (admin)
        payload = {
            "lead_id": sample_lead.id,
            "to_user_id": sales_rep_user.id,
            "reason": "Transfer reason",
        }
        create_resp = await client.post(
            "/api/v1/lead-transfer-requests/",
            json=payload,
            headers=auth_headers(admin_token),
        )
        assert create_resp.status_code == 201
        transfer_id = create_resp.json()["id"]

        # Now approve as manager using PATCH
        approve_resp = await client.patch(
            f"/api/v1/lead-transfer-requests/{transfer_id}",
            json={"status": "approved"},
            headers=auth_headers(manager_token),
        )
        assert approve_resp.status_code == 200
        data = approve_resp.json()
        assert data["status"] == "approved"
