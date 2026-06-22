"""
test_tasks.py — smoke tests for /api/v1/tasks/*

Google Tasks sync is mocked in conftest.py (autouse fixture).

Covers:
- GET  /          → list tasks (RBAC filtered)
- POST /          → admin/manager can create and assign, sales_rep cannot
- PATCH /{id}     → update task (including marking complete)
- DELETE /{id}    → delete task
"""

import pytest
from datetime import datetime, timedelta, timezone
from tests.conftest import auth_headers


pytestmark = pytest.mark.asyncio


def future_date(offset_days: int) -> str:
    dt = datetime.now(timezone.utc).date() + timedelta(days=offset_days)
    return dt.isoformat()


@pytest.fixture
def task_payload(sales_rep_user):
    return {
        "user_id": sales_rep_user.id,
        "title": "Follow up with lead",
        "notes": "Call back after 3 PM",
        "due": future_date(3),
    }


class TestListTasks:
    async def test_admin_can_list_tasks(self, client, admin_token):
        resp = await client.get("/api/v1/tasks/", headers=auth_headers(admin_token))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_sales_rep_can_list_own_tasks(self, client, sales_rep_token):
        resp = await client.get("/api/v1/tasks/", headers=auth_headers(sales_rep_token))
        assert resp.status_code == 200

    async def test_unauthenticated_cannot_list(self, client):
        resp = await client.get("/api/v1/tasks/")
        assert resp.status_code == 401


class TestCreateTask:
    async def test_admin_can_create_task(self, client, admin_token, task_payload):
        resp = await client.post(
            "/api/v1/tasks/",
            json=task_payload,
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "Follow up with lead"
        assert body["status"] == "needsAction"
        assert "id" in body

    async def test_manager_can_create_task(self, client, manager_token, task_payload):
        resp = await client.post(
            "/api/v1/tasks/",
            json=task_payload,
            headers=auth_headers(manager_token)
        )
        assert resp.status_code == 201

    async def test_sales_rep_cannot_create_task(self, client, sales_rep_token, task_payload):
        resp = await client.post(
            "/api/v1/tasks/",
            json=task_payload,
            headers=auth_headers(sales_rep_token)
        )
        assert resp.status_code == 403

    async def test_create_task_missing_fields(self, client, admin_token):
        resp = await client.post(
            "/api/v1/tasks/",
            json={},
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 422


class TestUpdateTask:
    async def test_update_task_title(self, client, admin_token, task_payload):
        create_resp = await client.post(
            "/api/v1/tasks/",
            json=task_payload,
            headers=auth_headers(admin_token)
        )
        task_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"title": "Updated Task Title"},
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Task Title"

    async def test_mark_task_complete(self, client, admin_token, task_payload):
        create_resp = await client.post(
            "/api/v1/tasks/",
            json=task_payload,
            headers=auth_headers(admin_token)
        )
        assert create_resp.status_code == 201
        task_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/tasks/{task_id}",
            json={"status": "completed"},
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    async def test_update_nonexistent_task(self, client, admin_token):
        resp = await client.patch(
            "/api/v1/tasks/99999",
            json={"title": "Ghost"},
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 404


class TestDeleteTask:
    async def test_admin_can_delete_task(self, client, admin_token, task_payload):
        create_resp = await client.post(
            "/api/v1/tasks/",
            json=task_payload,
            headers=auth_headers(admin_token)
        )
        assert create_resp.status_code == 201
        task_id = create_resp.json()["id"]

        resp = await client.delete(
            f"/api/v1/tasks/{task_id}",
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 204

    async def test_delete_nonexistent_task(self, client, admin_token):
        resp = await client.delete(
            "/api/v1/tasks/99999",
            headers=auth_headers(admin_token)
        )
        assert resp.status_code == 404
