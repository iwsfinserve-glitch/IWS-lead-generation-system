"""
test_auth.py — smoke tests for /api/v1/auth/*

Covers:
- POST /login          → valid credentials, wrong password, unknown email
- GET  /me             → returns current user profile
- POST /register       → admin can create users, non-admin gets 403
- GET  /users          → admin/manager can list, sales_rep gets 403
"""

import pytest
from tests.conftest import auth_headers


pytestmark = pytest.mark.asyncio


class TestLogin:
    async def test_login_success(self, client, admin_user):
        resp = await client.post("/api/v1/auth/login", data={
            "username": admin_user.email,
            "password": "admin123",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    async def test_login_wrong_password(self, client, admin_user):
        resp = await client.post("/api/v1/auth/login", data={
            "username": admin_user.email,
            "password": "wrongpassword",
        })
        assert resp.status_code == 401

    async def test_login_unknown_email(self, client):
        resp = await client.post("/api/v1/auth/login", data={
            "username": "nobody@example.com",
            "password": "doesntmatter",
        })
        assert resp.status_code == 401

    async def test_login_missing_fields(self, client):
        resp = await client.post("/api/v1/auth/login", data={})
        assert resp.status_code == 422


class TestMe:
    async def test_get_me(self, client, admin_token, admin_user):
        resp = await client.get("/api/v1/auth/me", headers=auth_headers(admin_token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == admin_user.email
        assert body["role"] == "admin"
        assert "hashed_password" not in body
        assert "google_access_token" not in body

    async def test_get_me_unauthenticated(self, client):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    async def test_get_me_invalid_token(self, client):
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer not.a.real.token"}
        )
        assert resp.status_code == 401


class TestRegister:
    async def test_admin_can_register_user(self, client, admin_token):
        resp = await client.post("/api/v1/auth/register", json={
            "name": "New Sales Rep",
            "email": "newsalesrep@example.com",
            "password": "securepass123",
            "role": "sales_rep",
        }, headers=auth_headers(admin_token))
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "newsalesrep@example.com"
        assert body["role"] == "sales_rep"

    async def test_sales_rep_cannot_register(self, client, sales_rep_token):
        resp = await client.post("/api/v1/auth/register", json={
            "name": "Unauthorized",
            "email": "unauth@example.com",
            "password": "pass",
            "role": "sales_rep",
        }, headers=auth_headers(sales_rep_token))
        assert resp.status_code == 403

    async def test_manager_cannot_register(self, client, manager_token):
        resp = await client.post("/api/v1/auth/register", json={
            "name": "Unauthorized",
            "email": "unauth2@example.com",
            "password": "pass",
            "role": "sales_rep",
        }, headers=auth_headers(manager_token))
        assert resp.status_code == 403

    async def test_duplicate_email_rejected(self, client, admin_token, admin_user):
        resp = await client.post("/api/v1/auth/register", json={
            "name": "Duplicate",
            "email": admin_user.email,   # already exists
            "password": "pass123",
            "role": "sales_rep",
        }, headers=auth_headers(admin_token))
        assert resp.status_code == 409


class TestListUsers:
    async def test_admin_can_list_users(self, client, admin_token):
        resp = await client.get("/api/v1/auth/users", headers=auth_headers(admin_token))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_manager_can_list_users(self, client, manager_token):
        resp = await client.get("/api/v1/auth/users", headers=auth_headers(manager_token))
        assert resp.status_code == 200

    async def test_sales_rep_cannot_list_users(self, client, sales_rep_token):
        resp = await client.get("/api/v1/auth/users", headers=auth_headers(sales_rep_token))
        assert resp.status_code == 403
