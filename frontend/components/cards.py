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

import html
import streamlit as st
from typing import Callable, Optional
from core.constants import STATUS_CONFIG


# ── Classification Badge ─────────────────────────────────────────────────────────

# Visual palette — one deliberately distinct colour per tier so reps can
# glance and immediately know who the high-value client is.
_CLASSIFICATION_BADGE_STYLES: dict[str, tuple[str, str, str]] = {
    # tier        (bg_gradient_start,  bg_gradient_end,   text)  — all safe as inline CSS
    "hni":          ("#B8860B", "#8B6914", "HNI"),         # deep gold
    "professional": ("#3730A3", "#312E81", "PRO"),         # rich indigo
    "retail":       ("#475569", "#334155", "RETAIL"),      # slate
}


def classification_badge(tier: str | None, *, compact: bool = True) -> str:
    """Return an inline HTML badge for a client classification tier.

    Args:
        tier:    'hni' | 'professional' | 'retail' | None
        compact: If True returns a short abbreviation (HNI / PRO / RTL).
                 If False returns the full label.

    Returns:
        An HTML ``<span>`` string safe for st.markdown(unsafe_allow_html=True).
        For unclassified leads returns an empty string so callers don't need
        to guard against None themselves.
    """
    if not tier:
        return (
            '<span style="'
            'display:inline-block;'
            'padding:2px 7px;'
            'border-radius:10px;'
            'font-size:0.72rem;'
            'font-weight:600;'
            'color:#94a3b8;'
            'background:#f1f5f9;'
            'border:1px solid #e2e8f0;'
            'letter-spacing:0.3px;'
            'vertical-align:middle;'
            'margin-left:6px;'
            '">Unclassified</span>'
        )

    key = tier.lower()
    if key not in _CLASSIFICATION_BADGE_STYLES:
        return ""

    grad_start, grad_end, label_short = _CLASSIFICATION_BADGE_STYLES[key]
    label = label_short if compact else tier.upper()

    return (
        f'<span style="'
        f'display:inline-block;'
        f'padding:2px 8px;'
        f'border-radius:10px;'
        f'font-size:0.72rem;'
        f'font-weight:700;'
        f'color:#fff;'
        f'background:linear-gradient(135deg,{grad_start},{grad_end});'
        f'letter-spacing:0.4px;'
        f'vertical-align:middle;'
        f'margin-left:6px;'
        f'box-shadow:0 1px 3px rgba(0,0,0,0.25);'
        f'">{html.escape(label)}</span>'
    )


def render_lead_card(lead: dict, *, key_prefix: str = "card") -> bool:
    """Render a single lead as an interactive HTML card with overlay button.

    Args:
        lead:       Lead dict from the API (must have id, name, status, etc.).
        key_prefix: Unique prefix for the Streamlit button key.

    Returns:
        True if the card was clicked, False otherwise.
    """
    s = STATUS_CONFIG.get(lead["status"], {"abbr": "?", "bg": "#555"})

    safe_name = html.escape(str(lead.get('name') or ''))
    safe_prof = html.escape(str(lead.get('profession') or ''))
    safe_source = html.escape(str(lead.get('source_name') or 'N/A'))
    safe_rep = html.escape(str(lead.get('assigned_rep_name') or 'N/A'))
    tier_badge = classification_badge(lead.get('client_classification'), compact=True)

    html_str = f'''<div class="overlay-trigger" style="display:flex;border:1px solid rgba(54,57,62,0.3);
    border-radius:6px;margin-bottom:12px;overflow:hidden;height:75px;transition:transform 0.15s ease;
    background:white;"><div style="flex:1;padding:12px 16px;"><div style="display:flex;align-items:baseline;gap:6px;"
    ><span style="color:#333;font-size:1.1rem;font-weight:600;line-height:1.2;">{safe_name}</span>{tier_badge}<span style="color:#666;
    font-size:0.85rem;font-weight:400;line-height:1.2;margin-left:4px;">{safe_prof}</span></div><div style="margin-top:4px;">
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
    due = html.escape(str(task.get("due") or "N/A"))

    # Check if overdue
    if task.get("due") and task.get("status") == "needsAction":
        try:
            if datetime.strptime(task["due"], "%Y-%m-%d").date() < date.today():
                s = {"abbr": "O", "bg": "red", "label": "Overdue"}
        except Exception:
            pass

    safe_title = html.escape(str(task.get('title') or ''))
    safe_user = html.escape(str(task.get('user_name') or 'N/A'))
    
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
    mode_color = "#2196F3" if mode == "online" else "#4CAF50"
    mode_text = "ON" if mode == "online" else "IP"
    day_str = html.escape(str(appt.get("start_time", "")[:10]))
    time_str = html.escape(str(appt.get("start_time", "")[11:16]))

    # Status badge config
    _STATUS_CARD = {
        "upcoming":  ("#2196F3", "U"),
        "pending":   ("#FF9800", "P"),
        "completed": ("#4CAF50", "C"),
    }
    current_status = appt.get("status", "upcoming")
    status_color, status_abbr = _STATUS_CARD.get(current_status, ("#888", "?"))

    safe_title = html.escape(str(appt.get('title') or ''))
    safe_lead = html.escape(str(appt.get('lead_name') or 'N/A'))
    safe_location = html.escape(str(appt.get('location') or 'TBD'))

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
                background:{status_color}; min-width:36px; padding:0 6px;
            ">
                <span style="color:white; font-size:0.75rem; font-weight:700;">{status_abbr}</span>
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
    on_view: Optional[Callable] = None,
) -> None:
    """Render a single user directory card."""
    safe_name = html.escape(str(user.get('name') or ''))
    safe_email = html.escape(str(user.get('email') or ''))
    safe_role = html.escape(str((user.get('role') or '').replace('_', ' ').title()))

    html_str = f'<div class="overlay-trigger user-card-html" style="display:flex;border:1px solid rgba(54,57,62,0.3);border-radius:6px;margin-bottom:12px;overflow:hidden;height:75px;transition:transform 0.15s ease;background:white;"><div style="flex:1;padding:12px 16px;"><div style="display:flex;align-items:baseline;gap:10px;"><span style="color:#333;font-size:1.1rem;font-weight:600;line-height:1.2;">{safe_name}</span><span style="color:#666;font-size:0.85rem;font-weight:400;line-height:1.2;">{safe_email}</span></div><div style="margin-top:4px;"><span style="color:#777;font-size:0.8rem;font-weight:400;line-height:1.2;">Role: {safe_role}</span></div></div><div style="display:flex;align-items:center;justify-content:center;background:#555;min-width:64px;padding:0 14px;"><span style="color:white;font-size:0.85rem;font-weight:600;">{safe_role[0] if safe_role else "?"}</span></div></div>'
    st.markdown(html_str, unsafe_allow_html=True)

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
    on_view: Optional[Callable] = None,
) -> None:
    """Render a list of users as interactive cards."""
    for user in users:
        render_user_card(
            user,
            key_prefix=key_prefix,
            on_view=on_view,
        )


def render_notification_card(notif: dict, *, key_prefix: str = "notif_card") -> bool:
    """Render a single notification as a clean card showing Title and Notification Type."""
    notif_id = notif.get("id", 0)
    title = html.escape(str(notif.get("title") or "Due Date Change Request"))
    notif_type = html.escape(str(notif.get("notification_type") or "Due Date Change"))
    message = html.escape(str(notif.get("message") or ""))
    created = html.escape(str((notif.get("created_at") or "")[:16].replace("T", " ")))
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
    """Render a pending approval request card with approve/reject buttons."""
    req_id = req["id"]
    title = html.escape(str(req.get(title_field, f"Request #{req_id}")))
    created = html.escape(str((req.get("created_at") or "")[:16].replace("T", " ")))

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
