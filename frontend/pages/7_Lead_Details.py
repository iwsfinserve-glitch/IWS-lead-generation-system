"""
7_Lead_Details.py — Full-page Lead Details view.

Navigated to when a lead card is clicked anywhere in the app.
The calling page must set st.session_state.selected_lead_id before
calling st.switch_page("pages/7_Lead_Details.py").
"""
import html
import streamlit as st
import time
from datetime import datetime, date
from core.auth import require_login
from core import api_client
from core.state import state
from core.api_client import APIError, APIConflictError
from core.styles import inject_global_styles
from components.layout import render_sidebar
from components.modals import (
    STATUS_DISPLAY, STATUS_OPTIONS_API, STATUS_OPTIONS_DISPLAY,
    STATUS_CONFIG, status_span,
)

st.set_page_config(
    page_title="Lead Details",
    page_icon="",
    layout="wide",
)

inject_global_styles(drawer=True)

require_login()

TOKEN = state.token
USER = state.user or {}
USER_ROLE = USER.get("role", "sales_rep")

render_sidebar(key_suffix="lead_details")

# ── Guard: need a lead_id in session state ───────────────────────────
lead_id = st.session_state.get("selected_lead_id")
if not lead_id:
    st.warning("No lead selected.")
    if st.button("< Back to All Leads"):
        st.switch_page("pages/6_All_Leads.py")
    st.stop()

# ── Load lead ─────────────────────────────────────────────────────────
try:
    lead = api_client.get_lead(TOKEN, lead_id)
except APIError as e:
    st.error(f"Failed to load lead: {e}")
    if st.button("< Back to All Leads"):
        st.switch_page("pages/6_All_Leads.py")
    st.stop()

# ── Derived values ────────────────────────────────────────────────────
status_val   = lead.get("status", "new")
status_label = STATUS_DISPLAY.get(status_val, status_val)
s_cfg        = STATUS_CONFIG.get(status_val, {"abbr": "?", "bg": "#555"})
status_color = s_cfg["bg"]

user_id  = USER.get("id")
can_update = (user_id is not None) and (USER_ROLE in ("admin", "manager") or str(lead.get("assigned_rep_id")) == str(user_id))


@st.fragment
def render_ai_insights_section(lead_id: int, lead: dict, token: str):
    """Render AI Insights inside an isolated Streamlit fragment for non-blocking updates."""
    st.markdown("### AI Insights")

    try:
        timeline = api_client.get_timeline(token, lead_id)
    except APIError:
        timeline = []

    if not timeline:
        st.info("ℹ️ No interaction history recorded for this lead yet. Add a note, book an appointment, or update status to automatically generate AI insights & recommendations.")
        return

    pending_since = st.session_state.get(f"ai_refresh_pending_{lead_id}")
    if pending_since and (time.time() - pending_since) < 3.6:
        st.markdown(
            """
            <div style="
                background: linear-gradient(135deg, #f0f7ff 0%, #f9f0ff 100%);
                border: 1px dashed #0366d6; border-radius: 10px;
                padding: 20px; text-align: center; margin-bottom: 14px;
            ">
                <div style="font-size: 1.15rem; font-weight: 700; color: #0366d6; margin-bottom: 6px;">
                    AI is updating insights in background...
                </div>
                <div style="font-size: 0.88rem; color: #555;">
                    Analyzing recent interactions and recalculating score & best contact timing (~3s)...
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        time.sleep(1.8)
        api_client.get_lead_ai_score.clear()
        api_client.get_lead_ai_contact_timing.clear()
        st.rerun()
        return
    elif pending_since:
        st.session_state.pop(f"ai_refresh_pending_{lead_id}", None)

    score_data  = None
    timing_data = None
    try:
        score_data = api_client.get_lead_ai_score(token, lead_id)
    except APIError:
        pass
    try:
        timing_data = api_client.get_lead_ai_contact_timing(token, lead_id)
    except APIError:
        pass

    if score_data or lead.get("ai_score") is not None:
        label     = (score_data.get("label") if score_data else lead.get("ai_score_label")) or "warm"
        score_val = score_data.get("score") if score_data else lead.get("ai_score")
        label_colors = {"hot": "#d32f2f", "warm": "#f57c00", "cold": "#1976d2"}
        l_color  = label_colors.get(label.lower(), "#f57c00")
        score_display = f"Score: {int(score_val)}/100" if score_val is not None else "Scored"

        key_signals_html = (
            f'<div style="margin-top:10px;"><strong>Key Signals:</strong> <span style="color:#444;">'
            + ", ".join(html.escape(str(s)) for s in score_data["key_signals"]) + "</span></div>"
        ) if score_data and score_data.get("key_signals") else ""

        action_html = (
            f'<div style="margin-top:10px;padding:10px 14px;background:#f0f7ff;border-radius:6px;'
            f'border-left:3px solid #0366d6;font-size:0.88rem;">'
            f'<strong>Suggested Action:</strong> {html.escape(str(score_data["suggested_next_action"]))}</div>'
        ) if score_data and score_data.get("suggested_next_action") else ""

        reasoning_html = (
            f'<p style="margin:8px 0;font-size:0.92rem;color:#444;"><em>"{html.escape(str(score_data["reasoning"]))}"</em></p>'
        ) if score_data and score_data.get("reasoning") else ""

        safe_label = html.escape(str(label.upper()))
        safe_score_disp = html.escape(str(score_display))

        st.markdown(
            f"""
            <div style="background:rgba(0,0,0,0.02);border:1px solid rgba(0,0,0,0.08);
                border-left:4px solid {l_color};border-radius:10px;padding:16px 18px;margin-bottom:14px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                    <span style="font-weight:700;font-size:1.1rem;color:#222;">{safe_label} LEAD</span>
                    <span style="background:{l_color};color:white;font-weight:700;font-size:0.8rem;
                        padding:4px 12px;border-radius:12px;">{safe_score_disp}</span>
                </div>
                {reasoning_html}
                {key_signals_html}
                {action_html}
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.caption("No AI Lead Score generated yet. Add a note or update status to generate insights automatically.")

    if timing_data and timing_data.get("has_sufficient_data"):
        days_str   = ", ".join(html.escape(str(d)) for d in (timing_data.get("suggested_days") or [])) or "N/A"
        window_str = html.escape(str(timing_data.get("suggested_window") or "Flexible"))
        conf       = html.escape(str((timing_data.get("confidence") or "medium").upper()))
        safe_timing_reasoning = html.escape(str(timing_data.get("reasoning") or ""))
        st.markdown(
            f"""
            <div style="background:#fafafa;border:1px solid rgba(0,0,0,0.08);
                border-radius:10px;padding:14px 18px;margin-bottom:14px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                    <span style="font-weight:700;font-size:0.95rem;color:#333;">Best Time to Contact</span>
                    <span style="font-size:0.75rem;color:#666;border:1px solid #ddd;padding:2px 8px;border-radius:10px;">Confidence: {conf}</span>
                </div>
                <p style="margin:4px 0;font-size:0.9rem;color:#333;">
                    <strong>Days:</strong> {days_str} &nbsp;|&nbsp; <strong>Window:</strong> {window_str}
                </p>
                <p style="margin:4px 0 0 0;font-size:0.82rem;color:#666;"><em>{safe_timing_reasoning}</em></p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif timing_data and not timing_data.get("has_sufficient_data"):
        st.caption(f"Best Time to Contact: {timing_data.get('reasoning')}")

# ─────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────
back_col, _ = st.columns([1, 8])
with back_col:
    if st.button("< Back",type="primary", key="ld_back_btn"):
        # Return to whichever page navigated here
        origin = st.session_state.get("lead_details_origin", "pages/6_All_Leads.py")
        st.switch_page(origin)

safe_lead_name = html.escape(str(lead.get('name') or ''))
safe_lead_prof = html.escape(str(lead.get('profession') or ''))
safe_status_label = html.escape(str(status_label.upper()))

st.markdown(
    f"""
    <div style="display:flex; align-items:baseline; gap:14px; margin-top:4px; margin-bottom:4px;">
        <h1 style="margin:0; font-weight:800; font-size:2.2rem; color:#111;">{safe_lead_name}</h1>
        <span style="font-size:1.1rem; font-weight:400; color:#666;">{safe_lead_prof}</span>
        <span style="
            background:{status_color}; color:white;
            border-radius:6px; padding:4px 12px;
            font-size:0.8rem; font-weight:700;
            text-transform:uppercase; letter-spacing:0.5px;
        ">{status_label}</span>
    </div>
    """,
    unsafe_allow_html=True,
)
email   = lead.get("email")     or "N/A"
phone   = lead.get("phone_number") or "N/A"
address = lead.get("address")   or None
source  = lead.get("source_name") or "N/A"
rep     = lead.get("assigned_rep_name") or "N/A"
last_c  = lead.get("last_contact") or "N/A"

contactDetailsCSS = """
    <style>
    .contact-card {
        border: 1px solid rgba(54, 57, 62, 0.2);
        border-radius: 10px;
        padding: 18px 20px;
        background: white;
        margin-bottom: 20px;
    }
    .contact-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 14px;
        margin: 0;
    }
    .info-group {
        display: flex;
        flex-direction: column;
    }
    .info-label {
        font-size: 0.75rem;
        color: #888;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin: 0;
    }
    .info-value {
        font-weight: 600;
        color: #222;
        margin: 2px 0 0 0;
    }
    </style>
"""
st.markdown(contactDetailsCSS, unsafe_allow_html=True)
st.markdown(
    f"""
<div class="contact-card">
    <dl class="contact-grid">
        <div class="info-group">
            <dt class="info-label">Email</dt>
            <dd class="info-value">{email}</dd>
        </div>
        <div class="info-group">
            <dt class="info-label">Phone</dt>
            <dd class="info-value">{phone}</dd>
        </div>
        <div class="info-group">
            <dt class="info-label">Source</dt>
            <dd class="info-value">{source}</dd>
        </div>
        <div class="info-group">
            <dt class="info-label">Assigned Rep</dt>
            <dd class="info-value">{rep}</dd>
        </div>
        <div class="info-group">
            <dt class="info-label">Last Contact</dt>
            <dd class="info-value">{last_c}</dd>
        </div>
        <div class="info-group">
            <dt class="info-label">Address</dt>
            <dd class="info-value">{address}</dd>
        </div>
    </dl>
</div>
""",
        unsafe_allow_html=True,
    )
if USER_ROLE == "admin":
    empty_col, edit_col = st.columns([2,2])
    with edit_col:
        col_edit, col_del = st.columns(2)
        with col_edit:
            if st.button("Edit", use_container_width=True, key="admin_edit_lead"):
                from components.modals import edit_lead_dialog
                edit_lead_dialog(lead)
        with col_del:
            if st.button("Delete Lead", type="primary", use_container_width=True, key="admin_del_lead"):
                st.session_state[f"confirm_del_{lead_id}"] = True
        
        if st.session_state.get(f"confirm_del_{lead_id}", False):
            st.warning("Are you sure you want to permanently delete this lead? This cannot be undone.")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("Yes, Delete", type="primary", use_container_width=True, key="admin_del_lead_yes"):
                    try:
                        api_client.delete_lead(TOKEN, lead_id)
                        st.toast("Lead deleted successfully.")
                        st.session_state[f"confirm_del_{lead_id}"] = False
                        st.switch_page("pages/6_All_Leads.py")
                    except Exception as e:
                        st.error(f"Failed to delete: {e}")
            with col_no:
                if st.button("Cancel", use_container_width=True, key="admin_del_lead_no"):
                    st.session_state[f"confirm_del_{lead_id}"] = False
            st.rerun()        


# ─────────────────────────────────────────────────────────────────────
# TWO-COLUMN LAYOUT
# ─────────────────────────────────────────────────────────────────────
left_col, right_col = st.columns([6,4], gap="large")


# ═════════════════════════════════════════════════════════════════════
# LEFT COLUMN —  AI insights, Management actions
# ═════════════════════════════════════════════════════════════════════
with right_col:

    # ── Contact & Assignment Card ─────────────────────────────────────

    # ── AI Insights (Fragment) ────────────────────────────────────────
    render_ai_insights_section(lead_id, lead, TOKEN)

    

# ═════════════════════════════════════════════════════════════════════
# RIGHT COLUMN — Interaction Timeline
# ═════════════════════════════════════════════════════════════════════
st.markdown('<hr style="margin:10px 0 24px 0; border:none; border-top:1px solid #e0e0e0;">', unsafe_allow_html=True)

with left_col:
    if can_update:
        st.markdown("### Actions")

        with st.expander("Update Lead", expanded=True):
            current_idx = STATUS_OPTIONS_API.index(status_val) if status_val in STATUS_OPTIONS_API else 0

            status_sel_col, date_col = st.columns(2)
            with status_sel_col:
                new_status_display = st.selectbox(
                    "Change Status",
                    options=STATUS_OPTIONS_DISPLAY,
                    index=current_idx,
                    key="ld_status_sel",
                )
            with date_col:
                try:
                    current_date = (
                        datetime.strptime(lead["last_contact"], "%Y-%m-%d").date()
                        if lead.get("last_contact") else date.today()
                    )
                except Exception:
                    current_date = date.today()
                new_last_contact = st.date_input("Last Contact", value=current_date, key="ld_last_contact")
                
            save_btn, blnk = st.columns([4,2])
            with blnk:
                if st.button("Save Changes", use_container_width=True, type="primary", key="ld_save_lead"):
                    new_status_api = STATUS_OPTIONS_API[STATUS_OPTIONS_DISPLAY.index(new_status_display)]
                    update_data = {}
                    if new_status_api != status_val:
                        update_data["status"] = new_status_api
                    if new_last_contact.isoformat() != (lead.get("last_contact") or ""):
                        update_data["last_contact"] = new_last_contact.isoformat()

                    if update_data:
                        try:
                            api_client.update_lead(TOKEN, lead_id, update_data)
                            st.toast("Lead updated successfully!")
                            st.rerun()
                        except APIError as e:
                            st.error(f"Update failed: {e}")
                    else:
                        st.toast("No changes to save.")

        with st.expander("Transfer Lead"):
            try:
                all_reps = api_client.get_sales_reps(TOKEN)
                other_reps = [u for u in all_reps if u["id"] != user_id]
                if other_reps:
                    rep_options = {u["id"]: u["name"] for u in other_reps}
                    transfer_to = st.selectbox(
                        "Transfer to",
                        options=list(rep_options.keys()),
                        format_func=lambda x: rep_options[x],
                        key="ld_transfer_to",
                    )
                    transfer_reason = st.text_area(
                        "Reason (optional)",
                        placeholder="e.g. This lead is in the new rep's territory",
                        height=80,
                        key="ld_transfer_reason",
                    )
                    if st.button("Request Transfer", use_container_width=True, key="ld_transfer_submit"):
                        try:
                            data = {"lead_id": lead_id, "to_user_id": transfer_to}
                            if transfer_reason and transfer_reason.strip():
                                data["reason"] = transfer_reason.strip()
                            api_client.create_lead_transfer_request(TOKEN, data)
                            st.toast("Transfer request submitted!")
                            st.rerun()
                        except APIError as e:
                            st.error(f"Request failed: {e}")
                else:
                    st.info("No other sales reps available for transfer.")
            except APIError as e:
                st.error(f"Could not load reps: {e}")


    else:
        st.markdown("### Actions")
        if lead.get("status") in ("unassigned", "new") or lead.get("assigned_rep_id") is None:
            with st.container(border=True):
                st.markdown(
                    """
                    <div style="text-align: center; padding: 10px 0;">
                        <h4 style="margin: 0; color: #E65100;">⚡ Unassigned Lead</h4>
                        <p style="font-size: 0.88rem; color: #666; margin: 8px 0 14px 0;">
                            This lead is waiting for a representative. Claim it now to assign it to yourself and begin working!
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                if st.button("⚡ Claim This Lead", type="primary", use_container_width=True, key=f"ld_claim_btn_{lead_id}"):
                    try:
                        api_client.claim_lead(TOKEN, lead_id)
                        st.toast("Lead claimed successfully! Status updated to In Progress.")
                        st.rerun()
                    except APIConflictError as e:
                        st.error(f"⚠️ {e}")
                    except APIError as e:
                        st.error(f"Claim failed: {e}")
        else:
            with st.container(border=True):
                rep_name = lead.get('assigned_rep_name') or 'another representative'
                st.markdown(
                    f"""
                    <div style="padding: 6px 4px;">
                        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                            <span style="font-size: 1.2rem;">🔒</span>
                            <strong style="color: #333; font-size: 0.95rem;">Read-Only Mode</strong>
                        </div>
                        <p style="font-size: 0.85rem; color: #555; margin: 0; line-height: 1.4;">
                            This lead is assigned to <strong>{rep_name}</strong>. You can view contact details, AI insights, and the interaction history, but only the assigned representative or a manager can modify status or add timeline notes.
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

    st.markdown("### Interaction History")

    # ── Add Note Form (only if can_update) ────────────────────────────
    if can_update:
        with st.form(key=f"ld_note_form_{lead_id}", clear_on_submit=True):
            new_note = st.text_area(
                "Add a note or interaction",
                height=100,
                placeholder="Enter call notes, follow-up details, or any interaction here...",
            )
            if st.form_submit_button("Add Note", use_container_width=True):
                if new_note.strip():
                    try:
                        api_client.add_timeline_note(TOKEN, lead_id, "note", {"note": new_note.strip()})
                        st.toast("Note added!")
                        st.rerun()
                    except APIError as e:
                        st.error(f"Failed to add note: {e}")
                else:
                    st.warning("Note cannot be empty.")

        st.markdown("<br>", unsafe_allow_html=True)

    # ── Timeline Feed ─────────────────────────────────────────────────
    _EVENT_STYLES = {
        "status_change":      {"border": "#2196F3", "bg": "#f0f7ff", "icon": ""},
        "note":               {"border": "#4CAF50", "bg": "#f0fff4", "icon": ""},
        "lead_created":       {"border": "#9C27B0", "bg": "#f9f0ff", "icon": ""},
        "appointment_booked": {"border": "#FF9800", "bg": "#fff8f0", "icon": ""},
    }

    try:
        timeline = api_client.get_timeline(TOKEN, lead_id)
    except APIError as e:
        st.error(f"Failed to load timeline: {e}")
        timeline = []

    if not timeline:
        st.caption("No timeline entries yet. Add a note above to get started.")
    else:
        for entry in timeline:
            ts         = entry["created_at"][:16].replace("T", " ")
            event_type = entry["event_type"]
            meta       = entry.get("event_metadata", {})
            style      = _EVENT_STYLES.get(event_type, {"border": "#999", "bg": "#f9f9f9", "icon": ""})

            # Build the content block per event type
            if event_type == "status_change":
                old = STATUS_DISPLAY.get(meta.get("old_status", ""), meta.get("old_status", ""))
                new = STATUS_DISPLAY.get(meta.get("new_status", ""), meta.get("new_status", ""))
                note_text = meta.get("note", "")
                body_html = (
                    f'<span style="font-weight:600;">{old}</span>'
                    f' &nbsp;-&gt;&nbsp; '
                    f'<span style="font-weight:600;color:#1565C0;">{new}</span>'
                )
                if note_text:
                    body_html += f'<br><em style="color:#555;font-size:0.88rem;">{note_text}</em>'

            elif event_type == "note":
                body_html = f'<span style="color:#333;">{meta.get("note", "")}</span>'

            elif event_type == "lead_created":
                body_html = f'Lead created from <strong>{meta.get("source", "unknown source")}</strong>'
                if meta.get("referred_by"):
                    body_html += f' (Referred by {meta["referred_by"]})'
                if meta.get("note"):
                    body_html += f'<br><em style="color:#555;font-size:0.88rem;">{meta["note"]}</em>'

            elif event_type == "appointment_booked":
                mode = meta.get("mode", "")
                loc  = meta.get("location", "")
                body_html = f'Appointment booked: <strong>{meta.get("title", "")}</strong>'
                if mode:
                    body_html += f' &nbsp;|&nbsp; {mode.replace("_", " ").title()}'
                if loc:
                    body_html += f' &nbsp;|&nbsp; {loc}'

            else:
                body_html = f'<span style="color:#555;">{event_type.replace("_", " ").title()}</span>'

            st.markdown(
                f"""
                <div style="
                    border-left:4px solid {style['border']};
                    background:{style['bg']};
                    border-radius:0 8px 8px 0;
                    padding:12px 16px;
                    margin-bottom:12px;
                ">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                        <span style="font-size:0.82rem;font-weight:600;color:#666;">
                            {event_type.replace('_', ' ').title()}
                        </span>
                        <span style="font-size:0.78rem;color:#999;">{ts}</span>
                    </div>
                    <div style="font-size:0.92rem;line-height:1.5;">{body_html}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
