"""
auth.py — Authentication check for all pages.

Uses browser cookies (via streamlit-cookies-controller) to persist the JWT
across browser refreshes.
"""

import streamlit as st
import asyncio
from streamlit_cookies_controller import CookieController
from core import api_client
from core.api_client import APIError, APIConnectionError
from core.state import state

@st.cache_resource
def get_cookie_controller() -> CookieController:
    return CookieController()

# Single shared controller instance, cached to survive re-runs.
controller = get_cookie_controller()
COOKIE_NAME = "lms_auth_token"

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
        saved_token = controller.get(COOKIE_NAME)
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
                    controller.remove(COOKIE_NAME)
                except (KeyError, AttributeError):
                    pass

    # ── No valid session — redirect to login ──
    st.switch_page("pages/0_Login.py")


def save_token_cookie(token: str):
    """Save the JWT to a browser cookie that survives page refreshes."""
    try:
        controller.set(COOKIE_NAME, token)
    except Exception:
        pass


def clear_token_cookie():
    """Remove the auth cookie (used on logout)."""
    try:
        controller.remove(COOKIE_NAME)
    except (KeyError, AttributeError, Exception):
        pass


def logout():
    """Full logout: clear session_state + cookie, then redirect to login."""
    clear_token_cookie()
    state.clear()
    st.switch_page("pages/0_Login.py")
