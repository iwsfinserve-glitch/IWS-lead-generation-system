"""
auth.py — Authentication check for all pages.

Uses browser cookies (via streamlit-cookies-controller) to persist the JWT
across browser refreshes.

SECURITY NOTES:
- CookieController is scoped to st.session_state (one instance per browser
  session), NOT @st.cache_resource (which is shared across ALL users on the
  server). This prevents session bleeding where User A's token is exposed
  to User B.
- Cookies are saved with secure=True (HTTPS only) and sameSite='Strict'
  (prevents CSRF attacks from third-party sites).
"""

import streamlit as st
from streamlit_cookies_controller import CookieController
from core import api_client
from core.api_client import APIError, APIConnectionError
from core.state import state

COOKIE_NAME = "lms_auth_token"
_SESSION_KEY = "_lms_cookie_controller"


def get_cookie_controller() -> CookieController:
    """
    Returns the CookieController for the current user's session.

    IMPORTANT: Stored in st.session_state (NOT @st.cache_resource) so that
    each browser tab/user gets a completely isolated controller instance.
    Using @st.cache_resource would share one controller across all users on
    the server, causing tokens to leak between sessions.
    """
    if _SESSION_KEY not in st.session_state:
        st.session_state[_SESSION_KEY] = CookieController()
    return st.session_state[_SESSION_KEY]

def require_login():
    """Check if user is logged in. Attempt cookie recovery if not."""

    # ── Fast path: session_state already has a token ──
    if state.token:
        if hasattr(st.session_state, '_pending_cookie_update'):
            save_token_cookie(st.session_state._pending_cookie_update)
            del st.session_state._pending_cookie_update
        return

    # ── Try to recover from browser cookie ──
    saved_token = None
    try:
        saved_token = get_cookie_controller().get(COOKIE_NAME)
    except Exception:
        pass

    import json
    if saved_token:
        try:
            token_dict = json.loads(saved_token)
            access_token = token_dict.get("access")
            refresh_token = token_dict.get("refresh")
        except Exception:
            # Fallback for old sessions that only stored the raw string
            access_token = saved_token
            refresh_token = None

        if access_token:
            try:
                user = api_client.get_me(access_token)
                state.token = access_token
                if refresh_token:
                    state.refresh_token = refresh_token
                state.user = user
                
                try:
                    api_client.get_users(access_token)
                    api_client.get_sources(access_token)
                except (APIError, APIConnectionError):
                    pass
                
                if hasattr(st.session_state, '_pending_cookie_update'):
                    save_token_cookie(st.session_state._pending_cookie_update)
                    del st.session_state._pending_cookie_update
                    
                return  # Successfully recovered
            except (APIError, APIConnectionError):
                # Token was invalid/expired or backend unreachable — clear stale cookie
                try:
                    get_cookie_controller().remove(COOKIE_NAME)
                except (KeyError, AttributeError):
                    pass

    # ── No valid session — redirect to login ──
    st.switch_page("pages/0_Login.py")


def save_token_cookie(token: str):
    """
    Save the JWT to a browser cookie that survives page refreshes.

    Security flags:
    - secure=True      : Cookie is only ever sent over HTTPS, never plain HTTP.
    - sameSite='Strict': Browser will refuse to send this cookie on any
                         cross-site request, blocking CSRF attacks.
    """
    try:
        get_cookie_controller().set(
            COOKIE_NAME,
            token,
            secure=True,
            same_site="Strict",
        )
    except Exception:
        pass


def clear_token_cookie():
    """Remove the auth cookie (used on logout)."""
    try:
        get_cookie_controller().remove(COOKIE_NAME)
    except (KeyError, AttributeError, Exception):
        pass


def logout():
    """Full logout: clear session_state + cookie, then redirect to login."""
    clear_token_cookie()
    state.clear()
    st.switch_page("pages/0_Login.py")
