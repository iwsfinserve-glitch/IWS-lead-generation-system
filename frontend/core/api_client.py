"""
api_client.py — Centralized HTTP client for the FastAPI backend.

Uses a persistent, pooled httpx.Client for connection reuse (keep-alive)
and a centralized _request() helper with automatic token refresh and
retry logic for transient errors.
"""

import httpx
import streamlit as st
import time
import json
from typing import List, Dict, Any, Optional
from core.config import settings

BASE_URL = settings.API_BASE_URL


# ── Custom Exception Hierarchy ───────────────────────────────────────

class APIError(Exception):
    """Base class for all API exceptions."""
    pass

class APIAuthError(APIError):
    """Raised when authentication fails (401/403)."""
    pass

class APIConnectionError(APIError):
    """Raised when the backend cannot be reached."""
    pass

class APIConflictError(APIError):
    """Raised on HTTP 409 Conflict — e.g. lead already claimed by another rep."""
    pass


# ── Persistent HTTP Client (connection pooling + keep-alive) ─────────

_http_client = httpx.Client(
    base_url=BASE_URL,
    timeout=30.0,
)

_report_client = httpx.Client(
    base_url=BASE_URL,
    timeout=90.0,
)


# ── Centralized Request Helper ───────────────────────────────────────

def _headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _handle_response(response: httpx.Response, raw_bytes: bool = False) -> Any:
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


def _request(
    method: str,
    endpoint: str,
    token: str | None = None,
    client: httpx.Client | None = None,
    raw_bytes: bool = False,
    **kwargs,
) -> Any:
    """Centralized HTTP request with token injection, auth refresh, and retries.

    - Injects Authorization header automatically.
    - On 401/403, attempts one token refresh via /auth/refresh before re-raising.
    - On transient errors (502/503/504 or connection failures), retries GET-like
      requests up to 2 times with exponential backoff.
    """
    from core.state import state

    http = client or _http_client
    headers = _headers(token) if token else {}

    is_read = method.upper() == "GET"
    max_retries = 2 if is_read else 0
    backoff = 0.5

    for attempt in range(max_retries + 1):
        try:
            resp = http.request(method, endpoint, headers=headers, **kwargs)
            return _handle_response(resp, raw_bytes=raw_bytes)
        except APIAuthError:
            # Try token refresh once
            if token and state.refresh_token:
                try:
                    refresh_resp = _http_client.post(
                        "/auth/refresh",
                        json={"refresh_token": state.refresh_token},
                    )
                    if refresh_resp.status_code == 200:
                        new_token = refresh_resp.json()["access_token"]
                        state.token = new_token
                        st.session_state._pending_cookie_update = json.dumps(
                            {"access": new_token, "refresh": state.refresh_token}
                        )
                        headers = _headers(new_token)
                        resp = http.request(method, endpoint, headers=headers, **kwargs)
                        return _handle_response(resp, raw_bytes=raw_bytes)
                except Exception:
                    pass
            raise
        except (APIConnectionError, APIError) as e:
            is_transient = (
                isinstance(e, APIConnectionError)
                or any(code in str(e) for code in ("502", "503", "504"))
            )
            if is_transient and attempt < max_retries:
                time.sleep(backoff * (2 ** attempt))
                continue
            raise
        except httpx.RequestError as e:
            if attempt < max_retries:
                time.sleep(backoff * (2 ** attempt))
                continue
            raise APIConnectionError(f"Could not connect to backend: {e}")


# ── Auth ─────────────────────────────────────────────────────────────

def login(email: str, password: str) -> Dict[str, Any]:
    """POST /auth/login — returns {access_token, token_type}."""
    return _request("POST", "/auth/login", data={"username": email, "password": password})

def get_me(token: str) -> Dict[str, Any]:
    """GET /auth/me — returns current user profile."""
    return _request("GET", "/auth/me", token=token)

@st.cache_data(ttl=300, show_spinner=False)
def get_users(token: str) -> List[Dict[str, Any]]:
    """GET /auth/users — list all users (admin/manager only)."""
    return _request("GET", "/auth/users", token=token)

@st.cache_data(ttl=300, show_spinner=False)
def get_sales_reps(token: str) -> List[Dict[str, Any]]:
    """GET /auth/sales-reps — list all sales_rep users (any authenticated user)."""
    return _request("GET", "/auth/sales-reps", token=token)

def register_user(token: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """POST /auth/register — create a new user (admin only)."""
    result = _request("POST", "/auth/register", token=token, json=data)
    get_users.clear()
    return result

def update_user(token: str, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """PATCH /auth/users/{user_id} — update a user."""
    result = _request("PATCH", f"/auth/users/{user_id}", token=token, json=data)
    get_users.clear()
    return result

def delete_user(token: str, user_id: int) -> None:
    """DELETE /auth/users/{user_id} — delete a user (admin only)."""
    _request("DELETE", f"/auth/users/{user_id}", token=token)
    get_users.clear()


def google_connect_url(token: str) -> str:
    """Build the backend URL that initiates the Google OAuth flow."""
    return f"{BASE_URL}/auth/google/connect?token={token}"

def get_google_status(token: str) -> Dict[str, Any]:
    """GET /auth/google/status — check whether Google Calendar is connected."""
    return _request("GET", "/auth/google/status", token=token)

def trigger_google_sync(token: str) -> Dict[str, Any]:
    """POST /auth/google/sync-appointments — start a background bulk calendar sync."""
    return _request("POST", "/auth/google/sync-appointments", token=token)

def google_disconnect(token: str) -> Dict[str, Any]:
    """DELETE /auth/google/disconnect — unlink Google Calendar from the current user."""
    return _request("DELETE", "/auth/google/disconnect", token=token)


# ── Sources ──────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def get_sources(token: str) -> List[Dict[str, Any]]:
    """GET /sources/ — list all lead sources."""
    return _request("GET", "/sources/", token=token)


# ── Leads ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def get_leads(
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
    return _request("GET", "/leads/", token=token, params=params)

@st.cache_data(ttl=300, show_spinner=False)
def get_leads_summary(token: str) -> Dict[str, Any]:
    """GET /leads/summary — optimized status counts."""
    return _request("GET", "/leads/summary", token=token)

@st.cache_data(ttl=300, show_spinner=False)
def get_lead(token: str, lead_id: int) -> Dict[str, Any]:
    """GET /leads/{id} — get single lead."""
    return _request("GET", f"/leads/{lead_id}", token=token)

def _clear_lead_caches():
    """Clear all lead-related caches after mutations."""
    get_leads.clear()
    get_lead.clear()
    get_timeline.clear()
    get_lead_ai_score.clear()
    get_lead_ai_contact_timing.clear()
    get_lead_ai_classification.clear()
    get_leads_summary.clear()

def create_lead(token: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """POST /leads/ — create a new lead."""
    result = _request("POST", "/leads/", token=token, json=data)
    _clear_lead_caches()
    return result

def update_lead(token: str, lead_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """PATCH /leads/{id} — update a lead."""
    result = _request("PATCH", f"/leads/{lead_id}", token=token, json=data)
    _clear_lead_caches()
    if "status" in data:
        st.session_state[f"ai_refresh_pending_{lead_id}"] = time.time()
    return result

def delete_lead(token: str, lead_id: int) -> None:
    """DELETE /leads/{id} — delete a lead."""
    _request("DELETE", f"/leads/{lead_id}", token=token)
    _clear_lead_caches()

def claim_lead(token: str, lead_id: int) -> Dict[str, Any]:
    """PATCH /leads/{id}/claim — atomically claim an unassigned lead.

    Raises APIConflictError (409) if the lead was claimed by someone else first.
    """
    try:
        resp = _http_client.request("PATCH", f"/leads/{lead_id}/claim", headers=_headers(token))
        if resp.status_code == 409:
            raise APIConflictError(resp.json().get("detail", "Lead already claimed."))
        result = _handle_response(resp)
        _clear_lead_caches()
        return result
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")


# ── Timeline ─────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def get_timeline(token: str, lead_id: int) -> List[Dict[str, Any]]:
    """GET /leads/{id}/timeline — get timeline entries."""
    return _request("GET", f"/leads/{lead_id}/timeline", token=token)

def add_timeline_note(token: str, lead_id: int, event_type: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """POST /leads/{id}/timeline — add a note/event."""
    result = _request(
        "POST", f"/leads/{lead_id}/timeline", token=token,
        json={"event_type": event_type, "event_metadata": metadata},
    )
    _clear_lead_caches()
    st.session_state[f"ai_refresh_pending_{lead_id}"] = time.time()
    return result


# ── Appointments ─────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def get_appointments(
    token: str,
    lead_id: Optional[int] = None,
    user_id: Optional[int] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """GET /appointments/ — list appointments, optionally filtered by status."""
    params: Dict[str, Any] = {}
    if lead_id:
        params["lead_id"] = lead_id
    if user_id is not None:
        params["user_id"] = user_id
    if status is not None:
        params["status"] = status
    return _request("GET", "/appointments/", token=token, params=params)

def create_appointment(token: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """POST /appointments/ — create appointment."""
    result = _request("POST", "/appointments/", token=token, json=data)
    get_appointments.clear()
    if data.get("lead_id"):
        st.session_state[f"ai_refresh_pending_{data['lead_id']}"] = time.time()
        get_lead_ai_score.clear()
        get_lead_ai_contact_timing.clear()
    return result

def update_appointment(token: str, appt_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """PATCH /appointments/{id} — update appointment."""
    result = _request("PATCH", f"/appointments/{appt_id}", token=token, json=data)
    get_appointments.clear()
    lead_id = data.get("lead_id") or st.session_state.get("selected_lead_id")
    if lead_id:
        st.session_state[f"ai_refresh_pending_{lead_id}"] = time.time()
        get_lead_ai_score.clear()
        get_lead_ai_contact_timing.clear()
    return result

def delete_appointment(token: str, appt_id: int) -> None:
    """DELETE /appointments/{id} — delete appointment."""
    _request("DELETE", f"/appointments/{appt_id}", token=token)
    get_appointments.clear()
    lead_id = st.session_state.get("selected_lead_id")
    if lead_id:
        st.session_state[f"ai_refresh_pending_{lead_id}"] = time.time()
        get_lead_ai_score.clear()
        get_lead_ai_contact_timing.clear()


# ── Tasks ────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def get_tasks(
    token: str,
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """GET /tasks/ — list tasks with pagination."""
    params: Dict[str, Any] = {"skip": skip, "limit": limit}
    if user_id is not None:
        params["user_id"] = user_id
    return _request("GET", "/tasks/", token=token, params=params)

def create_task(token: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """POST /tasks/ — create task."""
    result = _request("POST", "/tasks/", token=token, json=data)
    get_tasks.clear()
    return result

def update_task(token: str, task_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """PATCH /tasks/{id} — update task."""
    result = _request("PATCH", f"/tasks/{task_id}", token=token, json=data)
    get_tasks.clear()
    return result

def delete_task(token: str, task_id: int) -> None:
    """DELETE /tasks/{id} — delete task."""
    _request("DELETE", f"/tasks/{task_id}", token=token)
    get_tasks.clear()


# ── Reports ──────────────────────────────────────────────────────────

def get_lead_journey_report(token: str, lead_id: int) -> Dict[str, Any]:
    """GET /reports/lead-journey/{id} — returns JSON with narrative + timeline."""
    return _request("GET", f"/reports/lead-journey/{lead_id}", token=token, client=_report_client)

def download_lead_journey_report(token: str, lead_id: int) -> bytes:
    """GET /reports/lead-journey/{id}/download — returns .docx bytes."""
    return _request("GET", f"/reports/lead-journey/{lead_id}/download", token=token, client=_report_client, raw_bytes=True)

def get_periodic_leads_report(
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
    return _request("GET", "/reports/leads-periodic", token=token, client=_report_client, params=params)

def download_periodic_leads_report(
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
    return _request("GET", "/reports/leads-periodic/download", token=token, client=_report_client, raw_bytes=True, params=params)

def get_user_performance_report(
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
    return _request("GET", f"/reports/user-performance/{target_user_id}", token=token, client=_report_client, params=params)

def download_user_performance_report(
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
    return _request("GET", f"/reports/user-performance/{target_user_id}/download", token=token, client=_report_client, raw_bytes=True, params=params)

def get_team_performance_report(
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
    return _request("GET", "/reports/team-performance", token=token, client=_report_client, params=params)

def download_team_performance_report(
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
    return _request("GET", "/reports/team-performance/download", token=token, client=_report_client, raw_bytes=True, params=params)


# ── Self-Assigned Tasks ──────────────────────────────────────────────

def create_self_task(token: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """POST /tasks/self — create a task assigned to the current user."""
    result = _request("POST", "/tasks/self", token=token, json=data)
    get_tasks.clear()
    return result


# ── Due Date Requests ────────────────────────────────────────────────

def create_due_date_request(token: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """POST /due-date-requests/ — submit a due-date change request."""
    return _request("POST", "/due-date-requests/", token=token, json=data)

def get_due_date_requests(token: str) -> List[Dict[str, Any]]:
    """GET /due-date-requests/ — list due-date change requests."""
    return _request("GET", "/due-date-requests/", token=token)

def update_due_date_request(token: str, req_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """PATCH /due-date-requests/{id} — approve or reject a request."""
    return _request("PATCH", f"/due-date-requests/{req_id}", token=token, json=data)


# ── Notifications ────────────────────────────────────────────────────

def get_notifications(token: str, skip: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
    """GET /notifications/ — list current user's notifications."""
    return _request("GET", "/notifications/", token=token, params={"skip": skip, "limit": limit})

@st.cache_data(ttl=30, show_spinner=False)
def get_unread_notification_count(token: str) -> int:
    """GET /notifications/unread-count — returns count of unread notifications."""
    data = _request("GET", "/notifications/unread-count", token=token)
    return data.get("count", 0)

def mark_notification_read(token: str, notif_id: int) -> Dict[str, Any]:
    """PATCH /notifications/{id}/read — mark a single notification as read."""
    return _request("PATCH", f"/notifications/{notif_id}/read", token=token)

def mark_all_notifications_read(token: str) -> None:
    """PATCH /notifications/read-all — mark all notifications as read."""
    _request("PATCH", "/notifications/read-all", token=token)

def delete_notification(token: str, notif_id: int) -> None:
    """DELETE /notifications/{id} — delete a single notification."""
    try:
        resp = _http_client.request("DELETE", f"/notifications/{notif_id}", headers=_headers(token))
        if resp.status_code != 204:
            _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")

def clear_all_notifications(token: str) -> None:
    """DELETE /notifications/ — clear all notifications."""
    try:
        resp = _http_client.request("DELETE", "/notifications/", headers=_headers(token))
        if resp.status_code != 204:
            _handle_response(resp)
    except httpx.RequestError as e:
        raise APIConnectionError(f"Could not connect to backend: {e}")


# ── Lead Transfer Requests ───────────────────────────────────────────

def create_lead_transfer_request(token: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """POST /lead-transfer-requests/ — submit a lead transfer request."""
    result = _request("POST", "/lead-transfer-requests/", token=token, json=data)
    get_leads.clear()
    get_lead.clear()
    return result

def get_lead_transfer_requests(token: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """GET /lead-transfer-requests/ — list lead transfer requests."""
    params: Dict[str, Any] = {}
    if status:
        params["status"] = status
    return _request("GET", "/lead-transfer-requests/", token=token, params=params)

def update_lead_transfer_request(token: str, req_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """PATCH /lead-transfer-requests/{id} — approve or reject a transfer request."""
    result = _request("PATCH", f"/lead-transfer-requests/{req_id}", token=token, json=data)
    get_leads.clear()
    get_lead.clear()
    return result


# ── AI Insights ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def get_lead_ai_score(token: str, lead_id: int) -> Dict[str, Any]:
    """GET /leads/{lead_id}/ai/score — retrieve latest AI lead score."""
    return _request("GET", f"/leads/{lead_id}/ai/score", token=token, client=_report_client)

def run_lead_ai_score(token: str, lead_id: int) -> Dict[str, Any]:
    """POST /leads/{lead_id}/ai/score — run AI lead scoring."""
    result = _request("POST", f"/leads/{lead_id}/ai/score", token=token, client=_report_client)
    get_leads.clear()
    get_lead.clear()
    get_lead_ai_score.clear()
    return result

@st.cache_data(ttl=300, show_spinner=False)
def get_lead_ai_contact_timing(token: str, lead_id: int) -> Dict[str, Any]:
    """GET /leads/{lead_id}/ai/contact-timing — retrieve latest AI best time to contact."""
    return _request("GET", f"/leads/{lead_id}/ai/contact-timing", token=token, client=_report_client)

def run_lead_ai_contact_timing(token: str, lead_id: int) -> Dict[str, Any]:
    """POST /leads/{lead_id}/ai/contact-timing — run AI contact timing analysis."""
    result = _request("POST", f"/leads/{lead_id}/ai/contact-timing", token=token, client=_report_client)
    get_lead_ai_contact_timing.clear()
    return result


@st.cache_data(ttl=300, show_spinner=False)
def get_lead_ai_classification(token: str, lead_id: int) -> Dict[str, Any]:
    """GET /leads/{lead_id}/ai/client-classification — retrieve latest client classification."""
    return _request("GET", f"/leads/{lead_id}/ai/client-classification", token=token, client=_report_client)


def run_lead_ai_classification(token: str, lead_id: int) -> Dict[str, Any]:
    """POST /leads/{lead_id}/ai/client-classification — run / re-run client classification."""
    result = _request("POST", f"/leads/{lead_id}/ai/client-classification", token=token, client=_report_client)
    # Clear all lead caches so the updated classification badge propagates everywhere
    _clear_lead_caches()
    return result
