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
    <span style="color:#333;font-size:1.1rem;font-weight:600;line-height:1.2;">{safe_name}</span><span style="color:#666;
    font-size:0.85rem;font-weight:400;line-height:1.2;">{safe_prof}</span></div><div style="margin-top:4px;">
    <span style="color:#777;font-size:0.8rem;font-weight:400;line-height:1.2;">Source: {safe_source} | Rep: {safe_rep}</span>
    </div></div><div style="display:flex;align-items:center;justify-content:center;background:{s["bg"]};min-width:64px;padding:0 14px;">
    <span style="color:white;font-size:0.85rem;font-weight:600;">{s["abbr"]}</span></div></div>'''
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
            height: 75px;
            transition: all 0.2s;
            background: white;
        ">
            <div style="flex:1; padding:12px 16px; min-width:0; overflow:hidden;">
                <div style="display:flex; align-items:baseline; gap:10px;">
                    <span style="color:#333; font-size:1.1rem; font-weight:600; line-height:1.2; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; display:block; width:100%;">
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
                background: {s['bg']}; min-width:64px; padding:0 14px;
            ">
                <span style="color:white; font-size:0.85rem; font-weight:600;">
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
            <div style="flex:1; padding:12px 16px; min-width:0; overflow:hidden;">
                <div style="display:flex; align-items:baseline; justify-content:space-between; gap:8px;">
                    <span style="color:#333; font-size:1.1rem; font-weight:600; line-height:1.2; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:1; min-width:0;">
                        {safe_title}
                    </span>
                    <span style="color:#555; font-size:0.85rem; font-weight:500; white-space:nowrap; flex-shrink:0;">
                        {time_str}
                    </span>
                </div>
                <div style="margin-top:4px;">
                    <span style="color:red; font-size:0.9rem; font-weight:500;">
                        Date: {day_str}
                    </span>
                    <span style="color:#777; font-size:0.9rem; font-weight:500;">
                       &nbsp;|&nbsp; Lead: {safe_lead}
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

    html_str = f'<div class="overlay-trigger user-card-html" style="display:flex;border:1px solid rgba(54,57,62,0.3);border-radius:6px;margin-bottom:12px;overflow:hidden;height:75px;transition:transform 0.15s ease;background:white;"><div style="flex:1;padding:12px 16px;"><div style="display:flex;align-items:baseline;gap:10px;"><span style="color:#333;font-size:1.1rem;font-weight:600;line-height:1.2;">{safe_name}</span><span style="color:#666;font-size:0.85rem;font-weight:400;line-height:1.2;">{safe_email}</span></div><div style="margin-top:4px;"><span style="color:#777;font-size:0.8rem;font-weight:400;line-height:1.2;">Role: {safe_role}</span></div></div>{admin_buttons_html}<div style="display:flex;align-items:center;justify-content:center;background:#555;min-width:64px;padding:0 14px;"><span style="color:white;font-size:0.85rem;font-weight:600;">{safe_role[0]}</span></div></div>'
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


def render_notification_card(notif: dict, *, key_prefix: str = "notif_card") -> bool:
    """Render a single notification as a clean card showing Title and Notification Type.

    Returns True if clicked.
    """
    notif_id = notif.get("id", 0)
    title = bleach.clean(notif.get("title") or "Due Date Change Request")
    notif_type = bleach.clean(notif.get("notification_type") or "Due Date Change")
    message = bleach.clean(notif.get("message") or "")
    created = (notif.get("created_at") or "")[:16].replace("T", " ")
    is_read = notif.get("is_read", False)

    badge_bg = "#FFC107" if "Request" in notif_type else "#2196F3"
    border_color = "#ddd" if is_read else "#2196F3"

    html_str = f'''<div class="overlay-trigger" style="display:flex;border:1px solid rgba(54,57,62,0.3);
    border-left:4px solid {border_color};border-radius:6px;margin-bottom:10px;overflow:hidden;
    transition:transform 0.15s ease;background:white;"><div style="width:65px;background:{badge_bg};
    display:flex;flex-direction:column;align-items:center;justify-content:center;color:white;font-weight:700;
    font-size:0.75rem;padding:6px;text-align:center;">REQ</div><div style="flex:1;padding:12px 16px;">
    <div style="display:flex;align-items:baseline;justify-content:space-between;gap:10px;">
    <span style="color:#333;font-size:1.05rem;font-weight:700;line-height:1.2;">{title}</span>
    <span style="background:#f0f4f8;color:#0366d6;padding:2px 8px;border-radius:12px;font-size:0.75rem;font-weight:600;">{notif_type}</span>
    </div><div style="margin-top:4px;color:#555;font-size:0.88rem;">{message}</div>
    <div style="margin-top:4px;color:#888;font-size:0.75rem;">{created}</div></div></div>'''

    st.markdown(html_str, unsafe_allow_html=True)
    clicked = st.button("View", key=f"btn_{key_prefix}_{notif_id}", use_container_width=True)
    return clicked


def render_notification_cards(
    notifications: list[dict],
    *,
    key_prefix: str = "notif_card",
    on_click: Optional[Callable[[int], None]] = None,
) -> None:
    """Render a batch of notification cards."""
    for notif in notifications:
        clicked = render_notification_card(notif, key_prefix=key_prefix)
        if clicked and on_click:
            on_click(notif["id"])


def render_request_card(
    req: dict,
    *,
    key_prefix: str = "req_card",
    title_field: str = "lead_name",
    subtitle_html: str = "",
    detail_html: str = "",
    on_approve: Optional[Callable[[int], None]] = None,
    on_reject: Optional[Callable[[int], None]] = None,
) -> None:
    """Render a pending approval request card with approve/reject buttons.

    This is a reusable card used for both due-date requests (Tasks page)
    and lead transfer requests (All Leads page).

    Args:
        req:           Dict with at least 'id', 'created_at', and the title_field key.
        key_prefix:    Unique prefix for widget keys.
        title_field:   Key in req to use as the card title.
        subtitle_html: HTML string for the subtitle line (e.g. "From → To").
        detail_html:   HTML string for the detail/reason line.
        on_approve:    Callback(req_id) when Approve is clicked.
        on_reject:     Callback(req_id) when Reject is clicked.
    """
    req_id = req["id"]
    title = bleach.clean(str(req.get(title_field, f"Request #{req_id}")))
    created = (req.get("created_at") or "")[:16].replace("T", " ")

    st.markdown(f'''<div style="
        border: 1px solid rgba(54,57,62,0.2);
        border-left: 4px solid #FFC107;
        background: #fffdf0;
        padding: 16px 20px;
        border-radius: 8px;
        margin-bottom: 12px;
    ">
        <div style="display:flex; justify-content:space-between; align-items:baseline;">
            <span style="font-weight:700; font-size:1.05rem; color:#222;">{title}</span>
            <span style="font-size:0.75rem; color:#888;">{created}</span>
        </div>
        {f'<div style="margin-top:8px; font-size:0.9rem; color:#444;">{subtitle_html}</div>' if subtitle_html else ''}
        {f'<div style="margin-top:6px; font-size:0.85rem; color:#666; font-style:italic;">{detail_html}</div>' if detail_html else ''}
    </div>''', unsafe_allow_html=True)

    col_approve, col_reject = st.columns(2)
    with col_approve:
        if st.button("Approve", key=f"{key_prefix}_approve_{req_id}", use_container_width=True, type="primary"):
            if on_approve:
                on_approve(req_id)
    with col_reject:
        if st.button("Reject", key=f"{key_prefix}_reject_{req_id}", use_container_width=True):
            if on_reject:
                on_reject(req_id)
    st.markdown("")


def render_request_cards(
    requests: list[dict],
    *,
    key_prefix: str = "req_card",
    title_field: str = "lead_name",
    subtitle_fn: Optional[Callable[[dict], str]] = None,
    detail_fn: Optional[Callable[[dict], str]] = None,
    on_approve: Optional[Callable[[int], None]] = None,
    on_reject: Optional[Callable[[int], None]] = None,
) -> None:
    """Render a list of request cards with approve/reject actions.

    Args:
        requests:    List of request dicts.
        key_prefix:  Unique prefix for widget keys.
        title_field: Key in each request dict to use as card title.
        subtitle_fn: Optional function(req) → subtitle HTML string.
        detail_fn:   Optional function(req) → detail/reason HTML string.
        on_approve:  Callback(req_id) when Approve is clicked.
        on_reject:   Callback(req_id) when Reject is clicked.
    """
    for req in requests:
        subtitle = subtitle_fn(req) if subtitle_fn else ""
        detail = detail_fn(req) if detail_fn else ""
        render_request_card(
            req,
            key_prefix=key_prefix,
            title_field=title_field,
            subtitle_html=subtitle,
            detail_html=detail,
            on_approve=on_approve,
            on_reject=on_reject,
        )
