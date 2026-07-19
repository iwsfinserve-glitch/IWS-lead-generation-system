"""
api_client.py — Centralized HTTP async client for the FastAPI backend.

Refactored to use httpx for async non-blocking calls, with typed
responses and custom exception handling.
"""

import httpx
import streamlit as st
import asyncio
import functools
import time
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
    Also handles automatic token refresh on 401 APIAuthError and exponential backoff
    retries for transient network errors on read-only (GET) endpoints."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        from core.state import state
        
        is_get_request = func.__name__.startswith(("get_", "list_", "search_", "download_", "login")) or func.__name__ == "get_me"
        max_retries = 2 if is_get_request else 0
        backoff = 0.5
        
        for attempt in range(max_retries + 1):
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
            except (APIConnectionError, APIError) as e:
                # Check if it's a transient server error (502, 503, 504) or network connection issue
                is_transient = (
                    isinstance(e, APIConnectionError) or 
                    (isinstance(e, APIError) and any(err_code in str(e) for err_code in ("502", "503", "504")))
                )
                if is_transient and attempt < max_retries:
                    import time
                    time.sleep(backoff * (2 ** attempt))
                    continue
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

@st.cache_data(ttl=300, show_spinner=False)
@run_sync
async def get_sales_reps(token: str) -> List[Dict[str, Any]]:
    """GET /auth/sales-reps — list all sales_rep users (any authenticated user)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/auth/sales-reps", headers=_headers(token))
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


def google_connect_url(token: str) -> str:
    """Build the backend URL that initiates the Google OAuth flow.

    Opens in the browser (via st.markdown / webbrowser) - not an API call itself.
    The backend endpoint validates the JWT, builds the Google consent URL, and
    redirects the browser there.
    """
    return f"{BASE_URL}/auth/google/connect?token={token}"


@run_sync
async def get_google_status(token: str) -> Dict[str, Any]:
    """GET /auth/google/status — check whether Google Calendar is connected."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/auth/google/status", headers=_headers(token))
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")


@run_sync
async def trigger_google_sync(token: str) -> Dict[str, Any]:
    """POST /auth/google/sync-appointments — start a background bulk calendar sync."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{BASE_URL}/auth/google/sync-appointments", headers=_headers(token))
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")


@run_sync
async def google_disconnect(token: str) -> Dict[str, Any]:
    """DELETE /auth/google/disconnect — unlink Google Calendar from the current user."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(f"{BASE_URL}/auth/google/disconnect", headers=_headers(token))
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")



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
            get_lead_ai_score.clear()
            get_lead_ai_contact_timing.clear()
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
            get_lead_ai_score.clear()
            get_lead_ai_contact_timing.clear()
            if "status" in data:
                st.session_state[f"ai_refresh_pending_{lead_id}"] = time.time()
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
            get_lead_ai_score.clear()
            get_lead_ai_contact_timing.clear()
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
            get_lead_ai_score.clear()
            get_lead_ai_contact_timing.clear()
            st.session_state[f"ai_refresh_pending_{lead_id}"] = time.time()
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
            if data.get("lead_id"):
                st.session_state[f"ai_refresh_pending_{data['lead_id']}"] = time.time()
                get_lead_ai_score.clear()
                get_lead_ai_contact_timing.clear()
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
            lead_id = data.get("lead_id") or st.session_state.get("selected_lead_id")
            if lead_id:
                st.session_state[f"ai_refresh_pending_{lead_id}"] = time.time()
                get_lead_ai_score.clear()
                get_lead_ai_contact_timing.clear()
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
            lead_id = st.session_state.get("selected_lead_id")
            if lead_id:
                st.session_state[f"ai_refresh_pending_{lead_id}"] = time.time()
                get_lead_ai_score.clear()
                get_lead_ai_contact_timing.clear()
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
async def get_lead_journey_report(token: str, lead_id: int) -> Dict[str, Any]:
    """GET /reports/lead-journey/{id} — returns JSON with narrative + timeline."""
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.get(f"{BASE_URL}/reports/lead-journey/{lead_id}", headers=_headers(token))
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def download_lead_journey_report(token: str, lead_id: int) -> bytes:
    """GET /reports/lead-journey/{id}/download — returns .docx bytes."""
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.get(f"{BASE_URL}/reports/lead-journey/{lead_id}/download", headers=_headers(token))
            return await _handle_response(resp, raw_bytes=True)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def get_periodic_leads_report(
    token: str,
    user_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    period: str = "All Time",
) -> Dict[str, Any]:
    """GET /reports/leads-periodic — JSON with narrative + metrics."""
    params: Dict[str, Any] = {"period": period}
    if user_id:
        params["user_id"] = user_id
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.get(f"{BASE_URL}/reports/leads-periodic", headers=_headers(token), params=params)
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def download_periodic_leads_report(
    token: str,
    user_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    period: str = "All Time",
) -> bytes:
    """GET /reports/leads-periodic/download — returns .docx bytes."""
    params: Dict[str, Any] = {"period": period}
    if user_id:
        params["user_id"] = user_id
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.get(f"{BASE_URL}/reports/leads-periodic/download", headers=_headers(token), params=params)
            return await _handle_response(resp, raw_bytes=True)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def get_user_performance_report(
    token: str,
    target_user_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    period: str = "All Time",
) -> Dict[str, Any]:
    """GET /reports/user-performance/{id} — JSON with narrative + metrics."""
    params: Dict[str, Any] = {"period": period}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.get(f"{BASE_URL}/reports/user-performance/{target_user_id}", headers=_headers(token), params=params)
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def download_user_performance_report(
    token: str,
    target_user_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    period: str = "All Time",
) -> bytes:
    """GET /reports/user-performance/{id}/download — returns .docx bytes."""
    params: Dict[str, Any] = {"period": period}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.get(f"{BASE_URL}/reports/user-performance/{target_user_id}/download", headers=_headers(token), params=params)
            return await _handle_response(resp, raw_bytes=True)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def get_team_performance_report(
    token: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    period: str = "All Time",
    manager_id: Optional[int] = None,
) -> Dict[str, Any]:
    """GET /reports/team-performance — JSON with narrative + metrics."""
    params: Dict[str, Any] = {"period": period}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    if manager_id:
        params["manager_id"] = manager_id
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.get(f"{BASE_URL}/reports/team-performance", headers=_headers(token), params=params)
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def download_team_performance_report(
    token: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    period: str = "All Time",
    manager_id: Optional[int] = None,
) -> bytes:
    """GET /reports/team-performance/download — returns .docx bytes."""
    params: Dict[str, Any] = {"period": period}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    if manager_id:
        params["manager_id"] = manager_id
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.get(f"{BASE_URL}/reports/team-performance/download", headers=_headers(token), params=params)
            return await _handle_response(resp, raw_bytes=True)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")


# ── Self-Assigned Tasks ──────────────────────────────────────────────

@run_sync
async def create_self_task(token: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """POST /tasks/self — create a task assigned to the current user."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{BASE_URL}/tasks/self", headers=_headers(token), json=data)
            get_tasks.clear()
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")


# ── Due Date Requests ────────────────────────────────────────────────

@run_sync
async def create_due_date_request(token: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """POST /due-date-requests/ — submit a due-date change request."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{BASE_URL}/due-date-requests/", headers=_headers(token), json=data)
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def get_due_date_requests(token: str) -> List[Dict[str, Any]]:
    """GET /due-date-requests/ — list due-date change requests."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/due-date-requests/", headers=_headers(token))
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def update_due_date_request(token: str, req_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """PATCH /due-date-requests/{id} — approve or reject a request."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(f"{BASE_URL}/due-date-requests/{req_id}", headers=_headers(token), json=data)
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")


# ── Notifications ────────────────────────────────────────────────────

@run_sync
async def get_notifications(token: str, skip: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
    """GET /notifications/ — list current user's notifications."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BASE_URL}/notifications/",
                headers=_headers(token),
                params={"skip": skip, "limit": limit},
            )
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@st.cache_data(ttl=30, show_spinner=False)
@run_sync
async def get_unread_notification_count(token: str) -> int:
    """GET /notifications/unread-count — returns count of unread notifications."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/notifications/unread-count", headers=_headers(token))
            data = await _handle_response(resp)
            return data.get("count", 0)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def mark_notification_read(token: str, notif_id: int) -> Dict[str, Any]:
    """PATCH /notifications/{id}/read — mark a single notification as read."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(f"{BASE_URL}/notifications/{notif_id}/read", headers=_headers(token))
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def mark_all_notifications_read(token: str) -> None:
    """PATCH /notifications/read-all — mark all notifications as read."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(f"{BASE_URL}/notifications/read-all", headers=_headers(token))
            await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")


@run_sync
async def delete_notification(token: str, notif_id: int) -> None:
    """DELETE /notifications/{id} — delete a single notification."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(f"{BASE_URL}/notifications/{notif_id}", headers=_headers(token))
            if resp.status_code != 204:
                await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")


@run_sync
async def clear_all_notifications(token: str) -> None:
    """DELETE /notifications/ — clear all notifications."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(f"{BASE_URL}/notifications/", headers=_headers(token))
            if resp.status_code != 204:
                await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")


# ── Lead Transfer Requests ───────────────────────────────────────────

@run_sync
async def create_lead_transfer_request(token: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """POST /lead-transfer-requests/ — submit a lead transfer request."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{BASE_URL}/lead-transfer-requests/", headers=_headers(token), json=data)
            get_leads.clear()
            get_lead.clear()
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def get_lead_transfer_requests(token: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """GET /lead-transfer-requests/ — list lead transfer requests."""
    params: Dict[str, Any] = {}
    if status:
        params["status"] = status
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{BASE_URL}/lead-transfer-requests/", headers=_headers(token), params=params)
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def update_lead_transfer_request(token: str, req_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """PATCH /lead-transfer-requests/{id} — approve or reject a transfer request."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.patch(f"{BASE_URL}/lead-transfer-requests/{req_id}", headers=_headers(token), json=data)
            get_leads.clear()
            get_lead.clear()
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")


# ── AI Insights ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
@run_sync
async def get_lead_ai_score(token: str, lead_id: int) -> Dict[str, Any]:
    """GET /leads/{lead_id}/ai/score — retrieve latest AI lead score."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(f"{BASE_URL}/leads/{lead_id}/ai/score", headers=_headers(token))
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def run_lead_ai_score(token: str, lead_id: int) -> Dict[str, Any]:
    """POST /leads/{lead_id}/ai/score — run AI lead scoring."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{BASE_URL}/leads/{lead_id}/ai/score", headers=_headers(token))
            get_leads.clear()
            get_lead.clear()
            get_lead_ai_score.clear()
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@st.cache_data(ttl=300, show_spinner=False)
@run_sync
async def get_lead_ai_contact_timing(token: str, lead_id: int) -> Dict[str, Any]:
    """GET /leads/{lead_id}/ai/contact-timing — retrieve latest AI best time to contact."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(f"{BASE_URL}/leads/{lead_id}/ai/contact-timing", headers=_headers(token))
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

@run_sync
async def run_lead_ai_contact_timing(token: str, lead_id: int) -> Dict[str, Any]:
    """POST /leads/{lead_id}/ai/contact-timing — run AI contact timing analysis."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{BASE_URL}/leads/{lead_id}/ai/contact-timing", headers=_headers(token))
            get_lead_ai_contact_timing.clear()
            return await _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")


