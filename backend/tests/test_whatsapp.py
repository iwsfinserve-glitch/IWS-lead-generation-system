"""
test_whatsapp.py — tests for WhatsApp privacy and role restrictions.

Verifies:
1. WhatsApp chats of each RM are strictly personal:
   - Sales reps only see their own assigned leads' chats.
   - Managers ONLY see their own assigned leads' chats (cannot see team members' chats).
   - Admins ONLY see their own assigned leads' chats (cannot see everyone's chats).
2. Direct access controls (403 Forbidden):
   - Viewing chat messages for unassigned leads is forbidden for Reps, Managers, and Admins.
   - Sending WhatsApp messages to unassigned leads is forbidden.
   - Deleting WhatsApp chats for unassigned leads is forbidden.
   - Syncing WhatsApp history for unassigned leads is forbidden.
3. Leads without chats list:
   - Only returns leads assigned to the authenticated user.
4. Instance status and QR access:
   - Cannot query or access another user's instance.
"""

from datetime import datetime, timezone
import pytest
import pytest_asyncio
from app.models.lead import Lead, LeadSource
from app.models.enums import LeadStatus
from app.models.whatsapp_message import WhatsAppMessage, MessageDirection, MessageStatus
from tests.conftest import auth_headers

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def rep_lead(db_session, lead_source, sales_rep_user):
    lead = Lead(
        name="Rep Lead",
        phone_number="919876543211",
        status=LeadStatus.in_progress,
        source_id=lead_source.id,
        assigned_rep_id=sales_rep_user.id,
    )
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)

    # Add a WhatsApp message for this lead
    msg = WhatsAppMessage(
        lead_id=lead.id,
        user_id=sales_rep_user.id,
        whatsapp_msg_id="rep_msg_1",
        instance_name=f"rep_{sales_rep_user.id}",
        sender_phone="919876543211",
        receiver_phone=sales_rep_user.phone_number,
        direction=MessageDirection.inbound,
        content="Hello Rep, this is private",
        status=MessageStatus.delivered,
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(msg)
    await db_session.commit()
    return lead


@pytest_asyncio.fixture
async def admin_assigned_lead(db_session, lead_source, admin_user):
    lead = Lead(
        name="Admin Lead",
        phone_number="919876543222",
        status=LeadStatus.in_progress,
        source_id=lead_source.id,
        assigned_rep_id=admin_user.id,
    )
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)

    # Add a WhatsApp message for admin's lead
    msg = WhatsAppMessage(
        lead_id=lead.id,
        user_id=admin_user.id,
        whatsapp_msg_id="admin_msg_1",
        instance_name=f"rep_{admin_user.id}",
        sender_phone="919876543222",
        receiver_phone=admin_user.phone_number,
        direction=MessageDirection.inbound,
        content="Hello Admin, this is admin private",
        status=MessageStatus.delivered,
        timestamp=datetime.now(timezone.utc),
    )
    db_session.add(msg)
    await db_session.commit()
    return lead


class TestWhatsAppPrivacy:
    async def test_sales_rep_only_sees_own_chats(
        self, client, sales_rep_token, rep_lead, admin_assigned_lead
    ):
        """Sales rep should only see chats for leads assigned to them."""
        resp = await client.get("/api/v1/whatsapp/chats", headers=auth_headers(sales_rep_token))
        assert resp.status_code == 200
        chats = resp.json()
        lead_ids = [c["lead_id"] for c in chats]
        assert rep_lead.id in lead_ids
        assert admin_assigned_lead.id not in lead_ids

    async def test_manager_does_not_see_rep_chats(
        self, client, manager_token, rep_lead, admin_assigned_lead
    ):
        """Manager should NOT see rep's chats or admin's chats."""
        resp = await client.get("/api/v1/whatsapp/chats", headers=auth_headers(manager_token))
        assert resp.status_code == 200
        chats = resp.json()
        lead_ids = [c["lead_id"] for c in chats]
        assert rep_lead.id not in lead_ids
        assert admin_assigned_lead.id not in lead_ids

    async def test_admin_does_not_see_rep_chats(
        self, client, admin_token, rep_lead, admin_assigned_lead
    ):
        """Admin should only see their own assigned chats, NOT rep's chats."""
        resp = await client.get("/api/v1/whatsapp/chats", headers=auth_headers(admin_token))
        assert resp.status_code == 200
        chats = resp.json()
        lead_ids = [c["lead_id"] for c in chats]
        assert rep_lead.id not in lead_ids
        assert admin_assigned_lead.id in lead_ids

    async def test_manager_cannot_get_rep_chat_messages(
        self, client, manager_token, rep_lead
    ):
        """Manager receives 403 when attempting to view chat history of rep's lead."""
        resp = await client.get(
            f"/api/v1/whatsapp/chats/{rep_lead.id}",
            headers=auth_headers(manager_token),
        )
        assert resp.status_code == 403
        assert "Access denied" in resp.json()["detail"]

    async def test_admin_cannot_get_rep_chat_messages(
        self, client, admin_token, rep_lead
    ):
        """Admin receives 403 when attempting to view chat history of rep's lead."""
        resp = await client.get(
            f"/api/v1/whatsapp/chats/{rep_lead.id}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 403
        assert "Access denied" in resp.json()["detail"]

    async def test_manager_cannot_send_message_to_rep_lead(
        self, client, manager_token, rep_lead
    ):
        """Manager receives 403 when attempting to send message to rep's lead."""
        resp = await client.post(
            f"/api/v1/whatsapp/chats/{rep_lead.id}/send",
            headers=auth_headers(manager_token),
            json={"content": "Unauthorized message"},
        )
        assert resp.status_code == 403

    async def test_admin_cannot_send_message_to_rep_lead(
        self, client, admin_token, rep_lead
    ):
        """Admin receives 403 when attempting to send message to rep's lead."""
        resp = await client.post(
            f"/api/v1/whatsapp/chats/{rep_lead.id}/send",
            headers=auth_headers(admin_token),
            json={"content": "Unauthorized message"},
        )
        assert resp.status_code == 403

    async def test_manager_cannot_delete_rep_chat(
        self, client, manager_token, rep_lead
    ):
        """Manager receives 403 when attempting to delete rep's chat."""
        resp = await client.delete(
            f"/api/v1/whatsapp/chats/{rep_lead.id}",
            headers=auth_headers(manager_token),
        )
        assert resp.status_code == 403

    async def test_admin_cannot_delete_rep_chat(
        self, client, admin_token, rep_lead
    ):
        """Admin receives 403 when attempting to delete rep's chat."""
        resp = await client.delete(
            f"/api/v1/whatsapp/chats/{rep_lead.id}",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 403

    async def test_manager_cannot_sync_history_for_rep_lead(
        self, client, manager_token, rep_lead
    ):
        """Manager receives 403 when attempting to sync history for rep's lead."""
        resp = await client.post(
            f"/api/v1/whatsapp/chats/{rep_lead.id}/sync-history",
            headers=auth_headers(manager_token),
        )
        assert resp.status_code == 403

    async def test_leads_without_chats_scoped_to_user(
        self, client, sales_rep_token, manager_token, admin_token, db_session, lead_source, sales_rep_user, admin_user
    ):
        """Leads without chats must only return leads assigned to the requesting user."""
        rep_fresh_lead = Lead(
            name="Rep Fresh Lead",
            phone_number="919999990001",
            status=LeadStatus.in_progress,
            source_id=lead_source.id,
            assigned_rep_id=sales_rep_user.id,
        )
        admin_fresh_lead = Lead(
            name="Admin Fresh Lead",
            phone_number="919999990002",
            status=LeadStatus.in_progress,
            source_id=lead_source.id,
            assigned_rep_id=admin_user.id,
        )
        db_session.add_all([rep_fresh_lead, admin_fresh_lead])
        await db_session.commit()

        # Sales rep check
        resp_rep = await client.get("/api/v1/whatsapp/leads/without-chats", headers=auth_headers(sales_rep_token))
        assert resp_rep.status_code == 200
        rep_ids = [l["id"] for l in resp_rep.json()]
        assert rep_fresh_lead.id in rep_ids
        assert admin_fresh_lead.id not in rep_ids

        # Admin check
        resp_admin = await client.get("/api/v1/whatsapp/leads/without-chats", headers=auth_headers(admin_token))
        assert resp_admin.status_code == 200
        admin_ids = [l["id"] for l in resp_admin.json()]
        assert admin_fresh_lead.id in admin_ids
        assert rep_fresh_lead.id not in admin_ids

        # Manager check (has no assigned fresh leads)
        resp_mgr = await client.get("/api/v1/whatsapp/leads/without-chats", headers=auth_headers(manager_token))
        assert resp_mgr.status_code == 200
        mgr_ids = [l["id"] for l in resp_mgr.json()]
        assert rep_fresh_lead.id not in mgr_ids
        assert admin_fresh_lead.id not in mgr_ids

    async def test_instance_security(
        self, client, sales_rep_token, sales_rep_user, admin_token, admin_user
    ):
        """User cannot check status or QR for another user's instance."""
        # Rep trying to check admin's instance
        resp = await client.get(
            f"/api/v1/whatsapp/instances/status/rep_{admin_user.id}",
            headers=auth_headers(sales_rep_token),
        )
        assert resp.status_code == 403

        # Admin trying to check rep's instance
        resp2 = await client.get(
            f"/api/v1/whatsapp/instances/qr/rep_{sales_rep_user.id}",
            headers=auth_headers(admin_token),
        )
        assert resp2.status_code == 403
