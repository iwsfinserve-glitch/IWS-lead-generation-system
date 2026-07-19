"""
Tests for Notification endpoints (/api/v1/notifications/*).
"""

import pytest
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
