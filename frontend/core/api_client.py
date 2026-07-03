"""
api_client.py — Centralized HTTP async client for the FastAPI backend.

Refactored to use httpx for async non-blocking calls, with typed
responses and custom exception handling.
"""

import httpx
import streamlit as st
import asyncio
import functools
from typing import List, Dict, Any, Optional
from core.config import settings

BASE_URL = settings.API_BASE_URL


class APIError(Exception):
    """Base class for all API exceptions."""
    pass

class APIAuthError(APIError):
    """Raised when authentication fails (401/403)."""
    pass

class APIConnectionError(APIError):
    """Raised when the backend cannot be reached."""
    pass


def _headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}

async def _handle_response(response: httpx.Response, raw_bytes: bool = False) -> Any:
    """Centralized response handler to catch errors uniformly."""
    if response.status_code in (401, 403):
        raise APIAuthError(f"Authentication failed: {response.text}")
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise APIError(f"API Error ({e.response.status_code}): {e.response.text}")
    
    if raw_bytes:
        return response.content
    if response.status_code == 204:
        return None
    return response.json()

async def refresh_access_token_request(refresh_token: str) -> str:
    """Make the API call to refresh the access token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{BASE_URL}/auth/refresh", json={"refresh_token": refresh_token})
        if resp.status_code != 200:
            raise APIAuthError("Refresh token expired or invalid")
        return resp.json()["access_token"]

def run_sync(func):
    """Decorator to convert an async function to a sync function using asyncio.run.
    Also handles automatic token refresh on 401 APIAuthError."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        from core.state import state
        try:
            return asyncio.run(func(*args, **kwargs))
        except APIAuthError as e:
            # Don't try to refresh if the function failing was login itself
            if func.__name__ not in ("login",) and state.refresh_token:
                try:
                    new_token = asyncio.run(refresh_access_token_request(state.refresh_token))
                    state.token = new_token
                    
                    import json
                    import streamlit as st
                    st.session_state._pending_cookie_update = json.dumps({"access": new_token, "refresh": state.refresh_token})
                    
                    # Retry with the new token
                    if 'token' in kwargs:
                        kwargs['token'] = new_token
                    elif len(args) > 0:
                        args = (new_token,) + args[1:]
                    return asyncio.run(func(*args, **kwargs))
                except APIAuthError:
                    pass
            raise e
    return wrapper


# ── Auth ─────────────────────────────────────────────────────────────

@run_sync
async def login(email: str, password: str) -> Dict[str, Any]:
    """POST /auth/login — returns {access_token, token_type}."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{BASE_URL}/auth/login",
                data={"username": email, "password": password},
            )
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def get_me(token: str) -> Dict[str, Any]:
    """GET /auth/me — returns current user profile."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/auth/me", headers=_headers(token))
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@st.cache_data(ttl=300, show_spinner=False)
@run_sync
async def get_users(token: str) -> List[Dict[str, Any]]:
    """GET /auth/users — list all users (admin/manager only)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/auth/users", headers=_headers(token))
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def register_user(token: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """POST /auth/register — create a new user (admin only)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{BASE_URL}/auth/register", headers=_headers(token), json=data)
            get_users.clear()
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def update_user(token: str, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """PATCH /auth/users/{user_id} — update a user."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(f"{BASE_URL}/auth/users/{user_id}", headers=_headers(token), json=data)
            get_users.clear()
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def delete_user(token: str, user_id: int) -> None:
    """DELETE /auth/users/{user_id} — delete a user (admin only)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(f"{BASE_URL}/auth/users/{user_id}", headers=_headers(token))
            get_users.clear()
            await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")


# ── Lead Sources ─────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
@run_sync
async def get_sources(token: str) -> List[Dict[str, Any]]:
    """GET /sources/ — list all lead sources."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/sources/", headers=_headers(token))
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")


# ── Leads ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
@run_sync
async def get_leads(
    token: str, 
    status: Optional[str] = None, 
    assigned_rep_id: Optional[int] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """GET /leads/ — list leads with optional filters and pagination."""
    params: Dict[str, Any] = {"skip": skip, "limit": limit}
    if status:
        params["status"] = status
    if assigned_rep_id:
        params["assigned_rep_id"] = assigned_rep_id
    if search:
        params["search"] = search
        
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/leads/", headers=_headers(token), params=params)
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@st.cache_data(ttl=300, show_spinner=False)
@run_sync
async def get_lead(token: str, lead_id: int) -> Dict[str, Any]:
    """GET /leads/{id} — get single lead."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/leads/{lead_id}", headers=_headers(token))
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def create_lead(token: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """POST /leads/ — create a new lead."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{BASE_URL}/leads/", headers=_headers(token), json=data)
            get_leads.clear()
            get_lead.clear()
            get_timeline.clear()
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def update_lead(token: str, lead_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """PATCH /leads/{id} — update a lead."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(f"{BASE_URL}/leads/{lead_id}", headers=_headers(token), json=data)
            get_leads.clear()
            get_lead.clear()
            get_timeline.clear()
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def delete_lead(token: str, lead_id: int) -> None:
    """DELETE /leads/{id} — delete a lead."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(f"{BASE_URL}/leads/{lead_id}", headers=_headers(token))
            get_leads.clear()
            get_lead.clear()
            get_timeline.clear()
            await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")


# ── Timeline ─────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
@run_sync
async def get_timeline(token: str, lead_id: int) -> List[Dict[str, Any]]:
    """GET /leads/{id}/timeline — get timeline entries."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/leads/{lead_id}/timeline", headers=_headers(token))
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def add_timeline_note(token: str, lead_id: int, event_type: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """POST /leads/{id}/timeline — add a note/event."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{BASE_URL}/leads/{lead_id}/timeline",
                headers=_headers(token),
                json={"event_type": event_type, "event_metadata": metadata},
            )
            get_timeline.clear()
            get_leads.clear()
            get_lead.clear()
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")


# ── Appointments ─────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
@run_sync
async def get_appointments(token: str, lead_id: Optional[int] = None, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """GET /appointments/ — list appointments."""
    params: Dict[str, Any] = {}
    if lead_id:
        params["lead_id"] = lead_id
    if user_id is not None:
        params["user_id"] = user_id
        
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/appointments/", headers=_headers(token), params=params)
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def create_appointment(token: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """POST /appointments/ — create appointment."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{BASE_URL}/appointments/", headers=_headers(token), json=data)
            get_appointments.clear()
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def update_appointment(token: str, appt_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """PATCH /appointments/{id} — update appointment."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(f"{BASE_URL}/appointments/{appt_id}", headers=_headers(token), json=data)
            get_appointments.clear()
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def delete_appointment(token: str, appt_id: int) -> None:
    """DELETE /appointments/{id} — delete appointment."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(f"{BASE_URL}/appointments/{appt_id}", headers=_headers(token))
            get_appointments.clear()
            await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")


# ── Tasks ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
@run_sync
async def get_tasks(
    token: str,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """GET /tasks/ — list tasks with pagination."""
    params: Dict[str, Any] = {"skip": skip, "limit": limit}
    if user_id is not None:
        params["user_id"] = user_id
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/tasks/", headers=_headers(token), params=params)
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def create_task(token: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """POST /tasks/ — create task."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{BASE_URL}/tasks/", headers=_headers(token), json=data)
            get_tasks.clear()
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def update_task(token: str, task_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """PATCH /tasks/{id} — update task."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(f"{BASE_URL}/tasks/{task_id}", headers=_headers(token), json=data)
            get_tasks.clear()
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def delete_task(token: str, task_id: int) -> None:
    """DELETE /tasks/{id} — delete task."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(f"{BASE_URL}/tasks/{task_id}", headers=_headers(token))
            get_tasks.clear()
            await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")


# ── Reports ──────────────────────────────────────────────────────────

@run_sync
async def download_lead_journey_report(token: str, lead_id: int) -> bytes:
    """GET /reports/lead-journey/{id} — returns .docx bytes."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{BASE_URL}/reports/lead-journey/{lead_id}", headers=_headers(token))
            return await _handle_response(resp, raw_bytes=True)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def download_team_performance_report(token: str) -> bytes:
    """GET /reports/team-performance — returns .docx bytes."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{BASE_URL}/reports/team-performance", headers=_headers(token))
            return await _handle_response(resp, raw_bytes=True)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")
