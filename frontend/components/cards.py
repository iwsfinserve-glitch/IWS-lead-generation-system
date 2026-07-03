"""
cards.py — Reusable card rendering widgets for the Streamlit frontend.

Extracts the HTML card generation + overlay button pattern that was
duplicated across Dashboard and All Leads pages.

Usage:
    from components.cards import render_lead_card, render_lead_cards

    # Single card (returns True if clicked)
    if render_lead_card(lead, key_prefix="dash"):
        do_something(lead)

    # Batch render with auto-wired dialog
    render_lead_cards(leads, key_prefix="active_card", on_click=show_lead_panel)
"""

import streamlit as st
import bleach
from typing import Callable, Optional
from components.modals import STATUS_CONFIG


def render_lead_card(lead: dict, *, key_prefix: str = "card") -> bool:
    """Render a single lead as an interactive HTML card with overlay button.

    Args:
        lead:       Lead dict from the API (must have id, name, status, etc.).
        key_prefix: Unique prefix for the Streamlit button key.

    Returns:
        True if the card was clicked, False otherwise.
    """
    s = STATUS_CONFIG.get(lead["status"], {"abbr": "?", "bg": "#555"})

    safe_name = bleach.clean(lead['name'])
    safe_prof = bleach.clean(lead.get('profession') or '')
    safe_source = bleach.clean(lead.get('source_name') or 'N/A')
    safe_rep = bleach.clean(lead.get('assigned_rep_name') or 'N/A')

    html_str = f'''<div class="overlay-trigger" style="display:flex;border:1px solid rgba(54,57,62,0.3);
    border-radius:6px;margin-bottom:12px;overflow:hidden;height:75px;transition:transform 0.15s ease;
    background:white;"><div style="flex:1;padding:12px 16px;"><div style="display:flex;align-items:baseline;gap:10px;">
    <span style="color:#333;font-size:1.2rem;font-weight:600;line-height:1.2;">{safe_name}</span><span style="color:#666;
    font-size:0.85rem;font-weight:400;line-height:1.2;">{safe_prof}</span></div><div style="margin-top:4px;">
    <span style="color:#777;font-size:0.8rem;font-weight:400;line-height:1.2;">Source: {safe_source} | Rep: {safe_rep}</span>
    </div></div><div style="display:flex;align-items:center;justify-content:center;background:{s["bg"]};min-width:64px;padding:0 14px;">
    <span style="color:white;font-size:0.9rem;font-weight:600;">{s["abbr"]}</span></div></div>'''
    st.markdown(html_str, unsafe_allow_html=True)

    return st.button("Select", key=f"{key_prefix}_{lead['id']}", use_container_width=True)


def render_lead_cards(
    leads: list[dict],
    *,
    key_prefix: str = "card",
    on_click: Optional[Callable] = None,
) -> None:
    """Render a list of leads as clickable cards, optionally wiring clicks to a callback.

    Args:
        leads:      List of lead dicts from the API.
        key_prefix: Unique prefix for button keys (must differ per tab/page).
        on_click:   Optional callback(lead_id, status_bg_color) called on click.
                    Typically pass `show_lead_panel` from components.modals.
    """
    for lead in leads:
        if render_lead_card(lead, key_prefix=key_prefix):
            if on_click:
                s = STATUS_CONFIG.get(lead["status"], {"abbr": "?", "bg": "#555"})
                on_click(lead["id"], s["bg"])


def render_task_card(task: dict, *, key_prefix: str = "task_card") -> bool:
    """Render a single task as an interactive HTML card with overlay button."""
    from datetime import datetime, date
    status_config = {
        "needsAction": {"abbr": "P",  "bg": "#FFC107", "label": "Pending"},
        "completed":   {"abbr": "C",  "bg": "#4CAF50", "label": "Completed"},
    }
    s = status_config.get(task.get("status", "needsAction"), {"abbr": "?", "bg": "#555", "label": "Unknown"})
    due = task.get("due") or "N/A"

    # Check if overdue
    if task.get("due") and task.get("status") == "needsAction":
        try:
            if datetime.strptime(task["due"], "%Y-%m-%d").date() < date.today():
                s = {"abbr": "O", "bg": "red", "label": "Overdue"}
        except Exception:
            pass

    safe_title = bleach.clean(task['title'])
    safe_user = bleach.clean(task.get('user_name') or 'N/A')
    
    html_str = f"""
        <div class="overlay-trigger" style="
            display: flex;
            border: 1px solid rgba(54,57,62,0.3);
            border-radius: 6px;
            margin-bottom: 12px;
            height: 65px;
            transition: all 0.2s;
            background: white;
        ">
            <div style="flex:1; padding:10px 16px;">
                <div style="display:flex; align-items:baseline; gap:10px;">
                    <span style="color:#333; font-size:1.1rem; font-weight:600; line-height:1.2;">
                        {safe_title}
                    </span>
                </div>
                <div style="margin-top:4px; ">
                    <span style="color:#777; font-size:.9rem; font-weight:500; line-height:1.2;">
                        Assigned to: {safe_user} |
                    </span>
                    <span style="color:red; font-size:.9rem; font-weight:500; line-height:1.2;">
                        Due: {due}
                    </span>
                </div>
            </div>
            <div style="
                display:flex; align-items:center; justify-content:center;
                background: {s['bg']}; min-width:50px; padding:0 12px;
            ">
                <span style="color:white; font-size:0.75rem; font-weight:600;">
                    {s['abbr']}
                </span>
            </div>
        </div>
    """
    st.markdown(html_str, unsafe_allow_html=True)
    return st.button("Select", key=f"{key_prefix}_{task['id']}", use_container_width=True)


def render_task_cards(
    tasks: list[dict],
    *,
    key_prefix: str = "task_card",
    on_click: Optional[Callable] = None,
) -> None:
    """Render a list of tasks as clickable cards, optionally wiring clicks to a callback."""
    for task in tasks:
        if render_task_card(task, key_prefix=key_prefix):
            if on_click:
                on_click(task["id"])


def render_appointment_card(appt: dict, *, key_prefix: str = "appt_card") -> bool:
    """Render a single appointment as an interactive HTML card with overlay button."""
    mode = appt.get("mode", "online")
    mode_color, text = ("blue", "ON") if mode == "online" else ("#4CAF50", "IP")
    day_str = appt["start_time"][:10]
    time_str = appt["start_time"][11:16]
    
    safe_title = bleach.clean(appt['title'])
    safe_lead = bleach.clean(appt.get('lead_name') or 'N/A')
    safe_location = bleach.clean(appt.get('location') or 'TBD')

    html_str = f"""
        <div class="overlay-trigger" style="
            display: flex;
            border: 1px solid rgba(54,57,62,0.3);
            border-radius: 6px;
            margin-bottom: 12px;
            overflow: hidden;
            height: 75px;
            transition: all 0.2s;
            background: white;
        ">
            <div style="flex:1; padding:12px 16px;">
                <div style="display:flex; align-items:baseline; justify-content:space-between;">
                    <span style="color:#333; font-size:1.1rem; font-weight:600; line-height:1.2;">
                        {safe_title}
                    </span>
                    <span style="color:#555; font-size:0.85rem; font-weight:500;">
                        {time_str}
                    </span>
                </div>
                <div style="margin-top:4px;">
                    <span style="color:red; font-size:0.9rem; font-weight:500;">
                        Date: {day_str}
                    </span>
                    <span style="color:#777; font-size:0.9rem; font-weight:500;">
                       &nbsp;|&nbsp; Lead: {safe_lead} &nbsp;|&nbsp; {safe_location}
                    </span>
                </div>
            </div>
            <div style="
                display:flex; align-items:center; justify-content:center;
                background:{mode_color}; min-width:70px; padding:0 12px;
            ">
                <span style="color:white; font-size:0.75rem; font-weight:600;">
                    {text}
                </span>
            </div>
        </div>
    """
    st.markdown(html_str, unsafe_allow_html=True)
    return st.button("Select", key=f"{key_prefix}_{appt['id']}", use_container_width=True)


def render_appointment_cards(
    appts: list[dict],
    *,
    key_prefix: str = "appt_card",
    on_click: Optional[Callable] = None,
) -> None:
    """Render a list of appointments as clickable cards, optionally wiring clicks to a callback."""
    for appt in appts:
        if render_appointment_card(appt, key_prefix=key_prefix):
            if on_click:
                on_click(appt["id"])


def render_user_card(
    user: dict,
    *,
    key_prefix: str = "user_card",
    is_admin: bool = False,
    on_view: Optional[Callable] = None,
    on_edit: Optional[Callable] = None,
    on_delete: Optional[Callable] = None,
) -> None:
    """Render a single user directory card with role-based overlay buttons.

    Args:
        user:       User dict containing id, name, email, role, etc.
        key_prefix: Unique prefix for widget keys.
        is_admin:   If True, displays Edit and Delete buttons in addition to View.
        on_view:    Callback when View is clicked. If None, defaults to switching to 5_User_Details.py.
        on_edit:    Callback when Edit is clicked, passed the user dict.
        on_delete:  Callback when Delete is clicked, passed user["id"].
    """
    safe_name = bleach.clean(user['name'])
    safe_email = bleach.clean(user['email'])
    safe_role = bleach.clean(user['role'].replace('_', ' ').title())

    if is_admin:
        admin_buttons_html = '<div class="overlay-trigger" style="display:flex;align-items:center;justify-content:center;width:65px;"><span style="color:blue;font-weight:600;font-size:0.85rem;">Edit</span></div><div style="display:flex;align-items:center;justify-content:center;width:65px;"><span style="color:red;font-weight:600;font-size:0.85rem;">Delete</span></div>'
    else:
        admin_buttons_html = ''

    html_str = f'<div class="overlay-trigger user-card-html" style="display:flex;border:1px solid rgba(54,57,62,0.3);border-radius:6px;margin-bottom:12px;overflow:hidden;height:75px;transition:transform 0.15s ease;background:white;"><div style="flex:1;padding:12px 16px;"><div style="display:flex;align-items:baseline;gap:10px;"><span style="color:#333;font-size:1.2rem;font-weight:600;line-height:1.2;">{safe_name}</span><span style="color:#666;font-size:0.85rem;font-weight:400;line-height:1.2;">{safe_email}</span></div><div style="margin-top:4px;"><span style="color:#777;font-size:0.8rem;font-weight:400;line-height:1.2;">Role: {safe_role}</span></div></div>{admin_buttons_html}<div style="display:flex;align-items:center;justify-content:center;background:#555;min-width:64px;padding:0 14px;"><span style="color:white;font-size:0.9rem;font-weight:600;">{safe_role[0]}</span></div></div>'
    st.markdown(html_str, unsafe_allow_html=True)

    if is_admin:
        c_main, c_edit, c_del, c_pad = st.columns([15.5, 1.2, 1.2, 1.3])
        with c_main:
            if st.button(" ", key=f"{key_prefix}_view_{user['id']}", use_container_width=True):
                if on_view:
                    on_view(user["id"])
                else:
                    st.session_state.selected_user_id = user["id"]
                    st.switch_page("pages/5_User_Details.py")
        with c_edit:
            if st.button(" ", key=f"{key_prefix}_edit_{user['id']}", use_container_width=True):
                if on_edit:
                    on_edit(user)
        with c_del:
            if st.button(" ", key=f"{key_prefix}_del_{user['id']}", use_container_width=True):
                if on_delete:
                    on_delete(user["id"])
    else:
        c_main = st.columns(1)[0]
        with c_main:
            if st.button(" ", key=f"{key_prefix}_view_{user['id']}", use_container_width=True):
                if on_view:
                    on_view(user["id"])
                else:
                    st.session_state.selected_user_id = user["id"]
                    st.switch_page("pages/5_User_Details.py")


def render_user_cards(
    users: list[dict],
    *,
    key_prefix: str = "user_card",
    is_admin: bool = False,
    on_view: Optional[Callable] = None,
    on_edit: Optional[Callable] = None,
    on_delete: Optional[Callable] = None,
) -> None:
    """Render a list of users as interactive cards with role-based actions."""
    for user in users:
        render_user_card(
            user,
            key_prefix=key_prefix,
            is_admin=is_admin,
            on_view=on_view,
            on_edit=on_edit,
            on_delete=on_delete,
        )


