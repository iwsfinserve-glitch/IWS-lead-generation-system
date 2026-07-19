"""
layout.py — Shared UI layout components used across all pages.

Replaces the copy-pasted sidebar blocks that were duplicated in every
page file. Each page now calls render_sidebar() instead of manually
building the same 5-line block.
"""

import streamlit as st
from core.auth import logout
from core.state import state


def render_sidebar(*, key_suffix: str = "") -> None:
    """Render the standard sidebar with user info and logout button.

    Args:
        key_suffix: Optional suffix for the logout button key to prevent
                    duplicate widget ID errors across pages.  Pass a
                    unique string per page (e.g. "dash", "appt", "task").
    """
    user = state.user or {}
    logout_key = f"logout_{key_suffix}" if key_suffix else "logout"
    bell_key = f"bell_{key_suffix}" if key_suffix else "bell"

    with st.sidebar:
        st.markdown(f"**{user.get('name', '')}**")
        st.caption(
            f"{user.get('role', '').replace('_', ' ').title()}"
            + (f" - {user.get('email', '')}" if user.get("email") else "")
        )

        # ── Notification Bell ─────────────────────────────────────────
        if state.token:
            try:
                from core import api_client
                from core.api_client import APIError
                unread = api_client.get_unread_notification_count(state.token)
            except Exception:
                unread = 0

            badge_text = f"Notifications ({unread})" if unread > 0 else "Notifications"
            if st.button(badge_text, use_container_width=True, key=bell_key):
                from components.modals import show_notifications_panel
                show_notifications_panel()

        st.markdown("---")
        if st.button("Logout", use_container_width=True, key=logout_key):
            logout()


def render_pagination(total_items: int, page_key: str, page_size: int = 15) -> None:
    """Render Previous/Next pagination buttons and update session state page count.

    Args:
        total_items: Total number of items in the filtered collection.
        page_key:    Session state key storing the current page number (1-indexed).
        page_size:   Number of items displayed per page.
    """
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    current_page = st.session_state.get(page_key, 1)

    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        if current_page > 1:
            if st.button("Previous", use_container_width=True, key=f"prev_{page_key}"):
                st.session_state[page_key] = current_page - 1
                st.rerun()
    with c2:
        st.markdown(
            f"<p style='text-align:center; color:#888; margin-top:8px;'>Page {current_page} of {total_pages}</p>",
            unsafe_allow_html=True,
        )
    with c3:
        if current_page < total_pages:
            if st.button("Next", use_container_width=True, key=f"next_{page_key}"):
                st.session_state[page_key] = current_page + 1
                st.rerun()


def render_divider(*, margin_top: int = 0, margin_bottom: int = 10) -> None:
    """Render a styled horizontal rule divider.

    Replaces the inline '<hr style="...">' that was copy-pasted across
    6+ pages. Call this instead for consistent styling.
    """
    st.markdown(
        f'<hr style="height:1px;background:#d4d4d4;'
        f'margin-bottom:{margin_bottom}px;margin-top:{margin_top}px;">',
        unsafe_allow_html=True,
    )
