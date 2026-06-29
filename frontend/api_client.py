"""
api_client.py — Centralized HTTP client for the FastAPI backend.

All functions accept a JWT token and return parsed JSON or raw bytes.
Base URL defaults to http://localhost:8000/api/v1.
"""

import requests

BASE_URL = "http://localhost:8000/api/v1"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Auth ─────────────────────────────────────────────────────────────

def login(email: str, password: str) -> dict:
    """POST /auth/login — returns {access_token, token_type}."""
    resp = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": email, "password": password},
    )
    resp.raise_for_status()
    return resp.json()


def get_me(token: str) -> dict:
    """GET /auth/me — returns current user profile."""
    resp = requests.get(f"{BASE_URL}/auth/me", headers=_headers(token))
    resp.raise_for_status()
    return resp.json()


def get_users(token: str) -> list[dict]:
    """GET /auth/users — list all users (admin/manager only)."""
    resp = requests.get(f"{BASE_URL}/auth/users", headers=_headers(token))
    resp.raise_for_status()
    return resp.json()


# ── Lead Sources ─────────────────────────────────────────────────────

def get_sources(token: str) -> list[dict]:
    """GET /sources/ — list all lead sources."""
    resp = requests.get(f"{BASE_URL}/sources/", headers=_headers(token))
    resp.raise_for_status()
    return resp.json()


# ── Leads ────────────────────────────────────────────────────────────

def get_leads(token: str, status: str | None = None, search: str | None = None) -> list[dict]:
    """GET /leads/ — list leads with optional filters."""
    params = {}
    if status:
        params["status"] = status
    if search:
        params["search"] = search
    resp = requests.get(f"{BASE_URL}/leads/", headers=_headers(token), params=params)
    resp.raise_for_status()
    return resp.json()


def get_lead(token: str, lead_id: int) -> dict:
    """GET /leads/{id} — get single lead."""
    resp = requests.get(f"{BASE_URL}/leads/{lead_id}", headers=_headers(token))
    resp.raise_for_status()
    return resp.json()


def create_lead(token: str, data: dict) -> dict:
    """POST /leads/ — create a new lead."""
    resp = requests.post(f"{BASE_URL}/leads/", headers=_headers(token), json=data)
    resp.raise_for_status()
    return resp.json()


def update_lead(token: str, lead_id: int, data: dict) -> dict:
    """PATCH /leads/{id} — update a lead."""
    resp = requests.patch(f"{BASE_URL}/leads/{lead_id}", headers=_headers(token), json=data)
    resp.raise_for_status()
    return resp.json()


def delete_lead(token: str, lead_id: int) -> None:
    """DELETE /leads/{id} — delete a lead."""
    resp = requests.delete(f"{BASE_URL}/leads/{lead_id}", headers=_headers(token))
    resp.raise_for_status()


# ── Timeline ─────────────────────────────────────────────────────────

def get_timeline(token: str, lead_id: int) -> list[dict]:
    """GET /leads/{id}/timeline — get timeline entries."""
    resp = requests.get(f"{BASE_URL}/leads/{lead_id}/timeline", headers=_headers(token))
    resp.raise_for_status()
    return resp.json()


def add_timeline_note(token: str, lead_id: int, event_type: str, metadata: dict) -> dict:
    """POST /leads/{id}/timeline — add a note/event."""
    resp = requests.post(
        f"{BASE_URL}/leads/{lead_id}/timeline",
        headers=_headers(token),
        json={"event_type": event_type, "event_metadata": metadata},
    )
    resp.raise_for_status()
    return resp.json()


# ── Appointments ─────────────────────────────────────────────────────

def get_appointments(token: str, lead_id: int | None = None) -> list[dict]:
    """GET /appointments/ — list appointments."""
    params = {}
    if lead_id:
        params["lead_id"] = lead_id
    resp = requests.get(f"{BASE_URL}/appointments/", headers=_headers(token), params=params)
    resp.raise_for_status()
    return resp.json()


def create_appointment(token: str, data: dict) -> dict:
    """POST /appointments/ — create appointment."""
    resp = requests.post(f"{BASE_URL}/appointments/", headers=_headers(token), json=data)
    resp.raise_for_status()
    return resp.json()


def update_appointment(token: str, appt_id: int, data: dict) -> dict:
    """PATCH /appointments/{id} — update appointment."""
    resp = requests.patch(
        f"{BASE_URL}/appointments/{appt_id}", headers=_headers(token), json=data
    )
    resp.raise_for_status()
    return resp.json()


def delete_appointment(token: str, appt_id: int) -> None:
    """DELETE /appointments/{id} — delete appointment."""
    resp = requests.delete(
        f"{BASE_URL}/appointments/{appt_id}", headers=_headers(token)
    )
    resp.raise_for_status()


# ── Tasks ────────────────────────────────────────────────────────────

def get_tasks(token: str) -> list[dict]:
    """GET /tasks/ — list tasks."""
    resp = requests.get(f"{BASE_URL}/tasks/", headers=_headers(token))
    resp.raise_for_status()
    return resp.json()


def create_task(token: str, data: dict) -> dict:
    """POST /tasks/ — create task."""
    resp = requests.post(f"{BASE_URL}/tasks/", headers=_headers(token), json=data)
    resp.raise_for_status()
    return resp.json()


def update_task(token: str, task_id: int, data: dict) -> dict:
    """PATCH /tasks/{id} — update task."""
    resp = requests.patch(f"{BASE_URL}/tasks/{task_id}", headers=_headers(token), json=data)
    resp.raise_for_status()
    return resp.json()


def delete_task(token: str, task_id: int) -> None:
    """DELETE /tasks/{id} — delete task."""
    resp = requests.delete(f"{BASE_URL}/tasks/{task_id}", headers=_headers(token))
    resp.raise_for_status()


# ── Reports ──────────────────────────────────────────────────────────

def download_lead_journey_report(token: str, lead_id: int) -> bytes:
    """GET /reports/lead-journey/{id} — returns .docx bytes."""
    resp = requests.get(
        f"{BASE_URL}/reports/lead-journey/{lead_id}", headers=_headers(token)
    )
    resp.raise_for_status()
    return resp.content


def download_team_performance_report(token: str) -> bytes:
    """GET /reports/team-performance — returns .docx bytes."""
    resp = requests.get(
        f"{BASE_URL}/reports/team-performance", headers=_headers(token)
    )
    resp.raise_for_status()
    return resp.content
