"""
Tests for Notification endpoints (/api/v1/notifications/*).
"""

import pytest
from app.models.interaction import Notification
from tests.conftest import auth_headers


class TestNotifications:
    @pytest.mark.asyncio
    async def test_list_notifications(self, client, admin_token):
        """User can list their notifications."""
        resp = await client.get(
            "/api/v1/notifications/",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_unread_count(self, client, admin_token):
        """User can check unread notification count."""
        resp = await client.get(
            "/api/v1/notifications/unread-count",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 200
        assert "count" in resp.json()

    @pytest.mark.asyncio
    async def test_unauthenticated_cannot_list_notifications(self, client):
        resp = await client.get("/api/v1/notifications/")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_clear_all_notifications(self, client, admin_token):
        """User can clear all their notifications."""
        resp = await client.delete(
            "/api/v1/notifications/",
            headers=auth_headers(admin_token),
        )
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_user_cannot_see_or_modify_other_users_notifications(
        self, client, db_session, admin_user, sales_rep_user, admin_token, sales_rep_token
    ):
        """Each user only sees their own notifications and cannot modify other users'."""
        # Create a notification for admin
        admin_notif = Notification(
            user_id=admin_user.id,
            title="Admin Notice",
            message="Confidential admin notification",
            notification_type="System",
            is_read=False,
        )
        # Create a notification for sales rep
        rep_notif = Notification(
            user_id=sales_rep_user.id,
            title="Rep Notice",
            message="Sales rep notification",
            notification_type="System",
            is_read=False,
        )
        db_session.add_all([admin_notif, rep_notif])
        await db_session.commit()
        await db_session.refresh(admin_notif)
        await db_session.refresh(rep_notif)

        # Sales rep listing notifications: should see rep_notif, but NOT admin_notif
        rep_list_resp = await client.get(
            "/api/v1/notifications/",
            headers=auth_headers(sales_rep_token),
        )
        assert rep_list_resp.status_code == 200
        rep_items = rep_list_resp.json()
        rep_ids = [n["id"] for n in rep_items]
        assert rep_notif.id in rep_ids
        assert admin_notif.id not in rep_ids

        # Sales rep trying to mark Admin's notification as read: should be 404 (not found / forbidden)
        read_resp = await client.patch(
            f"/api/v1/notifications/{admin_notif.id}/read",
            headers=auth_headers(sales_rep_token),
        )
        assert read_resp.status_code == 404

        # Sales rep trying to delete Admin's notification: should be 404
        del_resp = await client.delete(
            f"/api/v1/notifications/{admin_notif.id}",
            headers=auth_headers(sales_rep_token),
        )
        assert del_resp.status_code == 404

        # Sales rep clearing all notifications: should only delete sales rep's notifications
        clear_resp = await client.delete(
            "/api/v1/notifications/",
            headers=auth_headers(sales_rep_token),
        )
        assert clear_resp.status_code == 204

        # Admin listing notifications: Admin's notification should still exist intact!
        admin_list_resp = await client.get(
            "/api/v1/notifications/",
            headers=auth_headers(admin_token),
        )
        assert admin_list_resp.status_code == 200
        admin_items = admin_list_resp.json()
        admin_ids = [n["id"] for n in admin_items]
        assert admin_notif.id in admin_ids
