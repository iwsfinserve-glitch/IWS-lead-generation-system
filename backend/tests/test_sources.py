"""
test_sources.py — smoke tests for /api/v1/sources/*

Covers:
- GET  /          → any auth user can list sources
- POST /          → admin/manager can create, sales_rep gets 403
- DELETE /{id}    → admin can delete, others get 403
"""

import pytest
from tests.conftest import auth_headers


pytestmark = pytest.mark.asyncio


class TestListSources:
    async def test_admin_can_list_sources(self, client, admin_token):
        resp = await client.get("/api/v1/sources/", headers=auth_headers(admin_token))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_sales_rep_can_list_sources(self, client, sales_rep_token):
        resp = await client.get("/api/v1/sources/", headers=auth_headers(sales_rep_token))
        assert resp.status_code == 200

    async def test_unauthenticated_cannot_list(self, client):
        resp = await client.get("/api/v1/sources/")
        assert resp.status_code == 401


class TestCreateSource:
    async def test_admin_can_create_source(self, client, admin_token):
        resp = await client.post("/api/v1/sources/", json={
            "name": "Client Referral",
            "priority": "high",
        }, headers=auth_headers(admin_token))
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Client Referral"
        assert "id" in body

    async def test_manager_can_create_source(self, client, manager_token):
        resp = await client.post("/api/v1/sources/", json={
            "name": "Wealth Seminar",
            "priority": "medium",
        }, headers=auth_headers(manager_token))
        assert resp.status_code == 201

    async def test_sales_rep_cannot_create_source(self, client, sales_rep_token):
        resp = await client.post("/api/v1/sources/", json={
            "name": "Blocked Source",
            "priority": "low",
        }, headers=auth_headers(sales_rep_token))
        assert resp.status_code == 403

    async def test_duplicate_source_name_rejected(self, client, admin_token, lead_source):
        resp = await client.post("/api/v1/sources/", json={
            "name": lead_source.name,   # already exists from fixture
            "priority": "low",
        }, headers=auth_headers(admin_token))
        assert resp.status_code == 409


class TestDeleteSource:
    async def test_admin_can_delete_source(self, client, admin_token, lead_source):
        resp = await client.delete(
            f"/api/v1/sources/{lead_source.id}",
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 204

    async def test_manager_cannot_delete_source(self, client, manager_token, lead_source):
        resp = await client.delete(
            f"/api/v1/sources/{lead_source.id}",
            headers=auth_headers(manager_token)
        )
        assert resp.status_code == 403

    async def test_delete_nonexistent_source(self, client, admin_token):
        resp = await client.delete(
            "/api/v1/sources/99999",
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 404
