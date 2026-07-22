"""
modals.py — Shared modal dialog components.

Extracts the lead detail drawer panel that was previously copy-pasted
between 1_Dashboard.py and 6_All_Leads.py.  Both pages now import
show_lead_panel() from here.

Usage:
    from components.modals import show_lead_panel
    show_lead_panel(lead_id, status_color)
"""

import html
import streamlit as st
import time
from datetime import datetime, date, timedelta
from core import api_client
from core.state import state
from core.api_client import APIError
from components.cards import classification_badge


# ── Shared Constants (re-exported for backwards compatibility) ───────
from core.constants import (                                           # noqa: F401
    STATUS_DISPLAY, STATUS_OPTIONS_API, STATUS_OPTIONS_DISPLAY,
    STATUS_CONFIG, ACTIVE_STATUSES,
)


# ── Helper Widgets ───────────────────────────────────────────────────
def status_span(status_type: str, bg_color: str) -> str:
    """Return an HTML badge span for a lead status."""
    safe_status = html.escape(str(status_type))
    return f"""
    <span style="
    border-radius: 6px;
    padding: 4px 8px;
    background-color: {bg_color};
    color: white;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    ">
        {safe_status}
    </span>
    """


def metric_card(label: str, value) -> str:
    """Return an HTML metric card for dashboard summary grids."""
    safe_label = html.escape(str(label))
    safe_val = html.escape(str(value))
    return f'<div style="border: 1px solid rgba(54,57,62,0.3); border-radius: 8px; padding: 20px; text-align: center; background-color: white;"><p style="color: #888; font-size: 0.85rem; margin: 0 0 8px 0; text-transform: uppercase; letter-spacing: 1px;">{safe_label}</p><p style="color: red; font-size: 2.2rem; font-weight: 700; margin: 0;">{safe_val}</p></div>'


# ── Lead Detail Drawer ───────────────────────────────────────────────
@st.dialog(" ", width="medium")
def show_lead_panel(lead_id: int, status_color: str) -> None:
    """Full-featured lead detail drawer with info, update form, and timeline.

    Opens as a right-side drawer (styled via the global CSS in core/styles.py).
    Provides:
      - Lead header (name + profession)
      - Detail fields (source, rep, email, phone, last contact, status)
      - Update form (status + last contact) — only for the assigned rep
      - Interaction history timeline with note-adding form
    """
    try:
        lead = api_client.get_lead(state.token, lead_id)
    except APIError as e:
        st.error(f"Failed to load lead: {e}")
        return

    display_status = STATUS_DISPLAY.get(lead["status"], lead["status"])

    safe_name = html.escape(str(lead.get("name") or ""))
    safe_prof = html.escape(str(lead.get("profession") or ""))
    tier = lead.get("client_classification")
    tier_badge_html = classification_badge(tier, compact=False)
    st.markdown(
        f'<h1 style="display:inline;font-weight:800;">{safe_name}</h1>'
        f'&nbsp;{tier_badge_html}&nbsp;'
        f'<h4 style="display:inline;font-weight:400;">{safe_prof}</h4>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # Details section
    st.markdown('<h2>Details</h2>', unsafe_allow_html=True)
    source_col, assignedTo_col = st.columns(2)
    with source_col: st.markdown(f"**Source:** {lead.get('source_name') or 'N/A'}")
    with assignedTo_col: st.markdown(f"**Assigned To:** {lead.get('assigned_rep_name') or 'N/A'}")

    email_col, phone_col = st.columns(2)
    with email_col: st.markdown(f"**Email:** {lead.get('email') or 'N/A'}")
    with phone_col: st.markdown(f"**Phone No:** {lead.get('phone_number') or 'N/A'}")

    lastContact_col, status_col = st.columns(2)
    with lastContact_col: st.markdown(f"**Last Contact:** {lead.get('last_contact') or 'N/A'}")
    with status_col: st.markdown(f"**Status:** {status_span(display_status, status_color)}", unsafe_allow_html=True)

    if lead.get("address"):
        st.markdown(f"**Address:** {lead['address']}")

    # ── AI Insights Section ──────────────────────────────────────────────
    st.markdown("---")
    st.markdown('<h2>AI Insights & Recommendations</h2>', unsafe_allow_html=True)

    try:
        timeline = api_client.get_timeline(state.token, lead_id)
    except APIError:
        timeline = []

    if not timeline:
        st.info("ℹ️ No interaction history recorded for this lead yet. Add a note, book an appointment, or update status to automatically generate AI insights & recommendations.")
    else:
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

        score_data = None
        timing_data = None
        try:
            score_data = api_client.get_lead_ai_score(state.token, lead_id)
        except APIError:
            pass

        try:
            timing_data = api_client.get_lead_ai_contact_timing(state.token, lead_id)
        except APIError:
            pass
        if score_data or lead.get("ai_score") is not None:
            label = (score_data.get("label") if score_data else lead.get("ai_score_label")) or "warm"
            score_val = score_data.get("score") if score_data else lead.get("ai_score")
            label_colors = {
                "hot": "#d32f2f",
                "warm": "#f57c00",
                "cold": "#1976d2",
            }
            l_color = label_colors.get(label.lower(), "#f57c00")

            score_display = f"Score: {int(score_val)}/100" if score_val is not None else "Scored"
            safe_reasoning = html.escape(str(score_data["reasoning"])) if score_data and score_data.get("reasoning") else ""
            safe_signals = ", ".join(html.escape(str(s)) for s in score_data["key_signals"]) if score_data and score_data.get("key_signals") else ""
            safe_action = html.escape(str(score_data["suggested_next_action"])) if score_data and score_data.get("suggested_next_action") else ""

            st.markdown(f"""
            <div style="background: rgba(0,0,0,0.02); border: 1px solid rgba(0,0,0,0.08); border-left: 4px solid {l_color}; border-radius: 8px; padding: 14px 16px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span style="font-weight: 700; font-size: 1.05rem; color: #222;">
                        {html.escape(label.upper())} LEAD
                    </span>
                    <span style="background: {l_color}; color: white; font-weight: 700; font-size: 0.8rem; padding: 3px 10px; border-radius: 12px;">
                        {html.escape(score_display)}
                    </span>
                </div>
                {f'<p style="margin: 6px 0; font-size: 0.92rem; color: #444;"><em>"{safe_reasoning}"</em></p>' if safe_reasoning else ''}
                {f'<div style="margin-top: 8px;"><strong>Key Signals:</strong> <span style="color: #444;">' + safe_signals + '</span></div>' if safe_signals else ''}
                {f'<div style="margin-top: 8px; padding: 8px 12px; background: #f0f7ff; border-radius: 6px; border-left: 3px solid #0366d6; font-size: 0.88rem;"><strong>Suggested Action:</strong> {safe_action}</div>' if safe_action else ''}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.caption("No AI Lead Score generated yet. Add a note or update status to generate insights automatically.")

        if timing_data and timing_data.get("has_sufficient_data"):
            days_str = ", ".join(html.escape(str(d)) for d in (timing_data.get("suggested_days") or [])) or "N/A"
            window_str = html.escape(str(timing_data.get("suggested_window") or "Flexible"))
            conf = html.escape(str((timing_data.get("confidence") or "medium").upper()))
            safe_timing_reasoning = html.escape(str(timing_data.get("reasoning") or ""))
            st.markdown(f"""
            <div style="background: #fafafa; border: 1px solid rgba(0,0,0,0.08); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span style="font-weight: 700; font-size: 0.95rem; color: #333;">Best Time to Contact</span>
                    <span style="font-size: 0.75rem; color: #666; border: 1px solid #ddd; padding: 2px 8px; border-radius: 10px;">Confidence: {conf}</span>
                </div>
                <p style="margin: 4px 0; font-size: 0.9rem; color: #333;">
                    <strong>Days:</strong> {days_str} &nbsp;|&nbsp; <strong>Window:</strong> {window_str}
                </p>
                <p style="margin: 4px 0 0 0; font-size: 0.82rem; color: #666;"><em>{safe_timing_reasoning}</em></p>
            </div>
            """, unsafe_allow_html=True)
        elif timing_data and not timing_data.get("has_sufficient_data"):
            st.caption(f"Best Time to Contact: {timing_data.get('reasoning')}")

        # ── Client Classification Panel ──────────────────────────────────────────
        # Try the detailed insight endpoint first (has confidence, key_indicators,
        # full reasoning). If it 404s, fall back to the denormalized field on the
        # lead dict which is always present after the first classification.
        cls_data = None
        try:
            cls_data = api_client.get_lead_ai_classification(state.token, lead_id)
        except APIError:
            pass

        _TIER_PALETTE = {
            "hni":          ("#B8860B", "#FFF8DC", "#7A5C00"),  # gold
            "professional": ("#3730A3", "#EEF2FF", "#1E1B4B"),  # indigo
            "retail":       ("#475569", "#F8FAFC", "#1E293B"),  # slate
        }

        if cls_data and cls_data.get("has_sufficient_data") and cls_data.get("classification"):
            tier = cls_data["classification"]
            conf_label = html.escape((cls_data.get("confidence") or "low").upper())
            safe_cls_reasoning = html.escape(str(cls_data.get("reasoning") or ""))
            indicators = cls_data.get("key_indicators") or []
            border_c, bg_c, text_c = _TIER_PALETTE.get(tier, ("#475569", "#F8FAFC", "#1E293B"))
            indicators_html = (
                "".join(
                    f'<li style="margin:2px 0;font-size:0.85rem;color:{text_c};">{html.escape(str(ind))}</li>'
                    for ind in indicators
                )
                if indicators else ""
            )
            generated = html.escape(str((cls_data.get("generated_at") or "")[:16]).replace("T", " "))
            st.markdown(f"""
            <div style="background:{bg_c};border:1px solid {border_c}40;
                        border-left:4px solid {border_c};
                        border-radius:8px;padding:14px 16px;margin-bottom:12px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                    <span style="font-weight:700;font-size:0.95rem;color:{text_c};">Client Tier Classification</span>
                    <div style="display:flex;gap:8px;align-items:center;">
                        <span style="font-size:0.75rem;color:#666;border:1px solid #ddd;
                                    padding:2px 8px;border-radius:10px;">Confidence: {conf_label}</span>
                        <span style="background:linear-gradient(135deg,{border_c},{border_c}cc);
                                    color:#fff;font-weight:700;font-size:0.8rem;
                                    padding:3px 12px;border-radius:12px;">{html.escape(tier.upper())}</span>
                    </div>
                </div>
                {f'<p style="margin:6px 0;font-size:0.9rem;color:{text_c};"><em>"{safe_cls_reasoning}"</em></p>' if safe_cls_reasoning else ''}
                {f'<ul style="margin:8px 0 0 0;padding-left:18px;">{indicators_html}</ul>' if indicators_html else ''}
                <div style="margin-top:8px;font-size:0.75rem;color:#888;">Last analysed: {generated}</div>
            </div>
            """, unsafe_allow_html=True)

        elif cls_data and not cls_data.get("has_sufficient_data"):
            # Sparse-data state — neutral/pending, not an error
            st.markdown("""
            <div style="background:#f8fafc;border:1px dashed #cbd5e1;border-radius:8px;
                        padding:12px 16px;margin-bottom:12px;">
                <div style="display:flex;align-items:center;gap:10px;">
                    <span style="font-size:1.2rem;">&#8987;</span>
                    <div>
                        <span style="font-weight:600;font-size:0.9rem;color:#475569;">Gathering Data for Classification</span><br>
                        <span style="font-size:0.82rem;color:#64748b;">Add more detailed interaction notes to unlock the AI client tier classification.</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        elif lead.get("client_classification"):
            # Fallback: show from the denormalized Lead field if the detailed endpoint fails
            tier = lead["client_classification"]
            border_c, bg_c, text_c = _TIER_PALETTE.get(tier, ("#475569", "#F8FAFC", "#1E293B"))
            st.markdown(f"""
            <div style="background:{bg_c};border:1px solid {border_c}40;
                        border-left:4px solid {border_c};border-radius:8px;
                        padding:12px 16px;margin-bottom:12px;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="font-weight:700;font-size:0.95rem;color:{text_c};">Client Tier</span>
                    <span style="background:linear-gradient(135deg,{border_c},{border_c}cc);
                                color:#fff;font-weight:700;font-size:0.8rem;
                                padding:3px 12px;border-radius:12px;">{html.escape(tier.upper())}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        else:
            st.caption("No client classification yet. Add interaction notes to trigger automatic classification.")

    # Check permissions: only assigned rep or admin/manager can update lead details
    user_id = (state.user or {}).get("id")
    user_role = (state.user or {}).get("role", "sales_rep")
    can_update = (user_id is not None) and (user_role in ("admin", "manager") or str(lead.get("assigned_rep_id")) == str(user_id))

    if can_update:
        st.markdown("---")

        # ── Re-classify Client Tier (authorized users only) ─────────────
        st.markdown('<h2>AI Actions</h2>', unsafe_allow_html=True)
        reclassify_col, _ = st.columns([1, 2])
        with reclassify_col:
            if st.button(
                "🔄 Re-classify Client Tier",
                key=f"reclassify_btn_{lead_id}",
                use_container_width=True,
                help="Force the AI to re-analyse all interaction notes and update the client tier. Downgrading is allowed.",
            ):
                with st.spinner("Running classification..."):
                    try:
                        cls_result = api_client.run_lead_ai_classification(state.token, lead_id)
                        new_tier = cls_result.get("classification")
                        if cls_result.get("has_sufficient_data") and new_tier:
                            st.toast(f"✅ Client re-classified as {new_tier.upper()}!", icon="🏷️")
                        else:
                            st.toast("⏳ Not enough data yet — add more detailed notes.", icon="📝")
                        api_client.get_lead_ai_classification.clear()
                        api_client.get_lead.clear()
                        st.rerun()
                    except APIError as e:
                        st.error(f"Re-classification failed: {e}")

        st.markdown("---")
        # Update Lead section
        st.markdown('<h2>Update Lead</h2>', unsafe_allow_html=True)

        current_idx = STATUS_OPTIONS_API.index(lead["status"]) if lead["status"] in STATUS_OPTIONS_API else 0

        status_col_u, date_col = st.columns(2)
        with status_col_u:
            new_status_display = st.selectbox(
                "Change Status",
                options=STATUS_OPTIONS_DISPLAY,
                index=current_idx,
            )
        with date_col:
            try:
                current_date = datetime.strptime(lead["last_contact"], "%Y-%m-%d").date() if lead.get("last_contact") else datetime.now().date()
            except:
                current_date = datetime.now().date()
            new_last_contact = st.date_input("Last Contact", value=current_date)

        if st.button("Update Lead Details", use_container_width=True, type="primary"):
            new_status_api = STATUS_OPTIONS_API[STATUS_OPTIONS_DISPLAY.index(new_status_display)]
            update_data = {}
            if new_status_api != lead["status"]:
                update_data["status"] = new_status_api
            if new_last_contact.isoformat() != (lead.get("last_contact") or ""):
                update_data["last_contact"] = new_last_contact.isoformat()

            if update_data:
                try:
                    api_client.update_lead(state.token, lead_id, update_data)
                    st.toast("Lead updated successfully!")
                except APIError as e:
                    st.error(f"Update failed: {e}")
            else:
                st.toast("No changes to save.")

        # ── Transfer Lead Section ─────────────────────────────────────
        st.markdown("")
        if st.toggle("Transfer Lead to Another Rep", key=f"transfer_toggle_{lead_id}"):
            try:
                all_reps = api_client.get_sales_reps(state.token)
                reps = [u for u in all_reps if u["id"] != user_id]
                if reps:
                    rep_options = {u["id"]: u["name"] for u in reps}
                    rep_ids = list(rep_options.keys())
                    transfer_to = st.selectbox(
                        "Transfer to",
                        options=rep_ids,
                        format_func=lambda x: rep_options[x],
                        key=f"transfer_to_{lead_id}",
                    )
                    transfer_reason = st.text_area(
                        "Note / Reason (optional)",
                        placeholder="e.g. This lead is in the new rep's territory",
                        height=80,
                        key=f"transfer_reason_{lead_id}",
                    )
                    if st.button("Request Transfer", use_container_width=True, key=f"transfer_submit_{lead_id}"):
                        try:
                            data = {"lead_id": lead_id, "to_user_id": transfer_to}
                            if transfer_reason and transfer_reason.strip():
                                data["reason"] = transfer_reason.strip()
                            api_client.create_lead_transfer_request(state.token, data)
                            st.toast("Transfer request submitted!")
                            st.rerun()
                        except APIError as e:
                            st.error(f"Request failed: {e}")
                else:
                    st.info("No other sales reps available for transfer.")
            except APIError as e:
                st.error(f"Could not load reps: {e}")

    st.markdown("---")

    # Interaction History
    st.markdown("<h2>Interaction History</h2>", unsafe_allow_html=True)
    if can_update:
        with st.form(key=f"note_form_{lead_id}", clear_on_submit=True):
            notes = st.text_area("Add a new note", height=100, placeholder="Enter call notes here...")
            submitted = st.form_submit_button("Add Note", use_container_width=True)
            if submitted and notes.strip():
                try:
                    api_client.add_timeline_note(state.token, lead_id, "note", {"note": notes.strip()})
                except APIError as e:
                    st.error(f"Failed to add note: {e}")

    # Show timeline
    st.markdown("<br>", unsafe_allow_html=True)
    try:
        timeline = api_client.get_timeline(state.token, lead_id)
        if timeline:
            for entry in timeline:
                ts = entry["created_at"][:16].replace("T", " ")
                event_type = entry["event_type"]
                meta = entry.get("event_metadata", {})
                
                if event_type == "status_change":
                    old = STATUS_DISPLAY.get(meta.get("old_status", ""), meta.get("old_status", ""))
                    new = STATUS_DISPLAY.get(meta.get("new_status", ""), meta.get("new_status", ""))
                    note_text = meta.get("note", "")
                    st.markdown(f"**{ts}** - `{old} -> {new}`\n\n_{note_text}_" if note_text else f"**{ts}** - `{old} -> {new}`")
                elif event_type == "note":
                    st.markdown(f"**{ts}** - _{meta.get('note', '')}_")
                elif event_type == "lead_created":
                    source_text = meta.get("source", "unknown source")
                    note_text = meta.get("note", "")
                    st.markdown(f"**{ts}** - Lead created from {source_text}\n\n_{note_text}_" if note_text else f"**{ts}** - Lead created from {source_text}")
                elif event_type == "appointment_booked":
                    st.markdown(f"**{ts}** - Appointment: {meta.get('title', '')}")
                else:
                    st.markdown(f"**{ts}** - {event_type}")
                st.markdown("---")
        else:
            st.caption("No timeline entries yet.")
    except APIError as e:
        st.error(f"Failed to load timeline: {e}")


# ── Task Detail Drawer ───────────────────────────────────────────────
@st.dialog(" ", width="medium")
def show_task_panel(task_id: int) -> None:
    """Full-featured task detail drawer with info and update/delete form."""
    tasks_pool = (
        (st.session_state.get("page_tasks") or [])
        + (st.session_state.get("assigned_tasks") or [])
        + (st.session_state.get("all_tasks") or [])
    )
    task = next((t for t in tasks_pool if t["id"] == task_id), None)
    if not task:
        try:
            tasks_pool = api_client.get_tasks(state.token, limit=1000)
            task = next((t for t in tasks_pool if t["id"] == task_id), None)
        except APIError:
            pass
    if not task:
        st.error("Task not found.")
        return

    user = state.user or {}
    current_user_id = user.get("id")
    current_role = user.get("role", "sales_rep")

    # Determine if the current user can freely edit the due date
    assigned_by = task.get("assigned_by")
    is_self_assigned = (assigned_by is None or assigned_by == current_user_id)
    can_edit_due = is_self_assigned or current_role in ("admin", "manager")

    safe_title = html.escape(str(task.get('title') or ''))
    st.markdown(f"""<h1 style="display: inline; font-weight: 800;">{safe_title}</h1>""", unsafe_allow_html=True)

    assigned_on = task.get("assigned_on", "")[:10]
    due = task.get("due") or "N/A"
    st.markdown(f"""<div style="margin-top:4px; ">
                    <span style="color:#444; font-size:.9rem; font-weight:500; line-height:1.2;">
                        Created: {assigned_on} |
                    </span>
                    <span style="color:red; font-size:.9rem; font-weight:500; line-height:1.2;">
                        Due: {due}
                    </span>
                </div>""", unsafe_allow_html=True)

    st.caption(f"Assigned to: {task.get('user_name', 'N/A')} | By: {task.get('assigned_by_name', 'N/A')}")
    st.markdown("---")

    col_due, col_status = st.columns(2)
    with col_due:
        try:
            due_val = datetime.strptime(task["due"], "%Y-%m-%d").date() if task.get("due") else date.today()
        except:
            due_val = date.today()

        if can_edit_due:
            new_due_date = st.date_input("Due Date", value=due_val, key=f"tsk_due_{task_id}")
        else:
            st.date_input("Due Date", value=due_val, key=f"tsk_due_{task_id}", disabled=True)
            new_due_date = None
    with col_status:
        status_options = ["needsAction", "completed"]
        status_display = {"needsAction": "Pending", "completed": "Completed"}
        current_status = task.get("status", "needsAction")
        new_status = st.selectbox("Status",
                                  options=status_options,
                                  index=status_options.index(current_status) if current_status in status_options else 0,
                                  format_func=lambda x: status_display.get(x, x),
                                  key=f"tsk_status_{task_id}")

    # ── Due Date Change Request (for manager-assigned tasks) ──────────
    if not can_edit_due and current_role == "sales_rep":
        st.markdown("")
        if st.toggle("Request Due Date Change", key=f"tsk_req_toggle_{task_id}"):
            req_col_date, req_col_reason = st.columns([1, 2])
            with req_col_date:
                req_new_date = st.date_input(
                    "New Due Date",
                    value=due_val,
                    key=f"tsk_req_date_{task_id}",
                )
            with req_col_reason:
                req_reason = st.text_input(
                    "Reason for change",
                    placeholder="e.g. Need more time for client follow-up",
                    key=f"tsk_req_reason_{task_id}",
                )
            if st.button("Submit Request", use_container_width=True, key=f"tsk_req_submit_{task_id}"):
                if not req_reason or not req_reason.strip():
                    st.warning("Please provide a reason.")
                else:
                    try:
                        api_client.create_due_date_request(state.token, {
                             "task_id": task_id,
                             "requested_date": req_new_date.isoformat(),
                             "reason": req_reason.strip(),
                        })
                        st.toast("Due date change request submitted!")
                        st.rerun()
                    except APIError as e:
                        st.error(f"Request failed: {e}")

    new_title = st.text_input("Title", value=task["title"], key=f"tsk_title_{task_id}")
    new_desc = st.text_area("Notes", value=task.get("notes") or "", height=150, key=f"tsk_desc_{task_id}")

    col_update, col_delete = st.columns(2)
    with col_update:
        if st.button("Save Changes", use_container_width=True, type="primary", key=f"tsk_save_{task_id}"):
            update_data = {}
            if new_title.strip() and new_title.strip() != task["title"]:
                update_data["title"] = new_title.strip()
            if new_desc.strip() != (task.get("notes") or ""):
                update_data["notes"] = new_desc.strip() or None
            if new_status != task.get("status"):
                update_data["status"] = new_status
            if can_edit_due and new_due_date is not None:
                if new_due_date.isoformat() != (task.get("due") or ""):
                    update_data["due"] = new_due_date.isoformat()

            if update_data:
                try:
                    api_client.update_task(state.token, task_id, update_data)
                    st.toast("Task updated!")
                    st.rerun()
                except APIError as e:
                    st.error(f"Update failed: {e}")
            else:
                st.toast("No changes.")
    with col_delete:
        if st.button("Delete Task", use_container_width=True, key=f"tsk_del_{task_id}"):
            try:
                api_client.delete_task(state.token, task_id)
                st.toast("Task deleted.")
                st.rerun()
            except APIError as e:
                st.error(f"Delete failed: {e}")


# ── Notifications Panel ──────────────────────────────────────────────
@st.dialog("Notifications", width="medium")
def show_notifications_panel() -> None:
    """Dialog showing the logged-in user's notifications with mark-read actions."""
    try:
        notifications = api_client.get_notifications(state.token, limit=50)
    except APIError as e:
        st.error(f"Failed to load notifications: {e}")
        return

    if not notifications:
        st.info("No notifications yet.")
        return

    # Top Action Button
    unread_count = sum(1 for n in notifications if not n.get("is_read"))
    if unread_count > 0:
        if st.button("Mark All Read", use_container_width=True, key="notif_mark_all"):
            try:
                api_client.mark_all_notifications_read(state.token)
                st.toast("All notifications marked as read!")
                st.rerun()
            except APIError as e:
                st.error(f"Failed: {e}")

    def get_notification_target_page(notif: dict) -> str:
        """Standardized routing from a notification to its respective Streamlit page."""
        link_type = (notif.get("link_type") or "").lower()
        notif_type = (notif.get("notification_type") or "").lower()
        msg = (notif.get("message") or "").lower()

        if link_type in ("task", "request") or "due date" in notif_type or "task" in notif_type or "due-date" in msg:
            return "pages/3_Tasks.py"
        elif link_type == "lead" or "lead" in notif_type:
            return "pages/6_All_Leads.py"
        elif link_type == "appointment" or "appointment" in notif_type:
            return "pages/2_Appointments.py"
        elif link_type == "report" or "report" in notif_type:
            return "pages/4_Reports.py"
        elif link_type == "user" or "user" in notif_type:
            return "pages/5_User_Details.py"
        return "pages/1_Dashboard.py"

    st.markdown("---")

    def format_notif_content(notif: dict):
        raw_title = notif.get("title")
        raw_type = notif.get("notification_type") or ""
        link_type = (notif.get("link_type") or "").lower()
        message = notif.get("message", "")

        # Determine source page type
        if raw_type in ("Tasks", "Leads", "Appointments", "Reports", "Users"):
            page_type = raw_type
        elif link_type in ("task", "request") or "due date" in raw_type.lower():
            page_type = "Tasks"
        elif link_type == "lead":
            page_type = "Leads"
        elif link_type == "appointment":
            page_type = "Appointments"
        elif link_type == "report":
            page_type = "Reports"
        elif link_type == "user":
            page_type = "Users"
        else:
            page_type = "Tasks"

        # Extract subject title without redundancy
        subject_title = raw_title
        if not subject_title or subject_title in ("Due Date Change Request", "Due Date Change Approved", "Due Date Change Rejected", "Tasks"):
            if '"' in message:
                parts = message.split('"')
                if len(parts) >= 3:
                    subject_title = parts[1]
            else:
                subject_title = "Task Notification"

        # Clean message body to avoid broken grammar
        import re
        clean_msg = message
        if subject_title:
            pattern = re.compile(r'\s*for\s*"' + re.escape(subject_title) + r'"\s*', re.IGNORECASE)
            clean_msg = pattern.sub(' ', clean_msg)
            clean_msg = re.sub(r'\s*for\s+to\s*', ' to ', clean_msg).strip()

        return subject_title, page_type, clean_msg

    for notif in notifications:
        is_read = notif.get("is_read", False)
        created = notif.get("created_at", "")[:16].replace("T", " ")
        subject_title, page_type, clean_msg = format_notif_content(notif)

        border_color = "#ddd" if is_read else "#2196F3"
        bg_color = "white" if is_read else "#f0f7ff"
        badge_color = "#0366d6"

        col_card, col_del = st.columns([6, 0.8])
        with col_card:
            safe_subj = html.escape(str(subject_title or ""))
            safe_ptype = html.escape(str(page_type or ""))
            safe_msg = html.escape(str(clean_msg or ""))
            safe_created = html.escape(str(created or ""))
            html_str = f'''<div class="overlay-trigger" style="display:flex; flex-direction:column; justify-content:space-between;
            border: 1px solid rgba(54,57,62,0.2); border-left: 4px solid {border_color}; background: {bg_color};
            padding: 12px 16px; border-radius: 6px; margin-bottom: 12px; min-height: 75px; transition: transform 0.15s ease;">
                <div style="display:flex; justify-content:space-between; align-items:baseline; gap:10px;">
                    <span style="font-weight:700; font-size:1.02rem; color:#222; line-height:1.3;">{safe_subj}</span>
                    <span style="font-size:0.75rem; font-weight:600; color:{badge_color}; background:rgba(0,0,0,0.06); padding:3px 8px; border-radius:12px; white-space:nowrap;">{safe_ptype}</span>
                </div>
                <div style="margin-top:6px; font-size:0.88rem; color:#444; line-height:1.4;">
                    {safe_msg}
                </div>
                <div style="margin-top:6px; font-size:0.75rem; color:#888; text-align:right;">
                    {safe_created}
                </div>
            </div>'''
            st.markdown(html_str, unsafe_allow_html=True)

            if st.button("Open", key=f"notif_open_{notif['id']}", use_container_width=True):
                try:
                    if not is_read:
                        api_client.mark_notification_read(state.token, notif["id"])
                except APIError:
                    pass
                target_page = get_notification_target_page(notif)
                st.switch_page(target_page)
        with col_del:
            st.markdown('<div style="height:14px;"></div>', unsafe_allow_html=True)
            if st.button("x", key=f"notif_del_{notif['id']}", help="Clear this notification"):
                try:
                    api_client.delete_notification(state.token, notif["id"])
                    st.toast("Notification cleared")
                    st.rerun()
                except APIError as e:
                    st.error(f"Failed: {e}")

    st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
    _, col_center, _ = st.columns([1, 1.5, 1])
    with col_center:
        if st.button("Clear All", use_container_width=True, key="notif_clear_all_bottom"):
            try:
                api_client.clear_all_notifications(state.token)
                st.toast("All notifications cleared!")
                st.rerun()
            except APIError as e:
                st.error(f"Failed: {e}")


# ── Appointment Detail Drawer ────────────────────────────────────────
@st.dialog(" ", width="medium")
def show_appointment_panel(appt_id: int) -> None:
    """Full-featured appointment detail drawer with update and delete form."""
    appts_pool = (
        (st.session_state.get("appointments") or [])
        + (st.session_state.get("user_appts") or [])
        + (st.session_state.get("all_appointments") or [])
    )
    appt = next((a for a in appts_pool if a["id"] == appt_id), None)
    if not appt:
        try:
            appts_pool = api_client.get_appointments(state.token)
            appt = next((a for a in appts_pool if a["id"] == appt_id), None)
        except APIError:
            pass
    if not appt:
        st.error("Appointment not found.")
        return

    # ── Status badge ────────────────────────────────────────────────────
    _STATUS_BADGE = {
        "upcoming":  ("#2196F3", "Upcoming"),
        "pending":   ("#FF9800", "Pending"),
        "completed": ("#4CAF50", "Completed"),
    }
    current_status = appt.get("status", "upcoming")
    badge_color, badge_label = _STATUS_BADGE.get(current_status, ("#888", current_status.title()))

    safe_title = html.escape(str(appt.get('title') or ''))
    safe_badge = html.escape(str(badge_label))
    st.markdown(
        f"""<h1 style="display:inline;font-weight:800;">{safe_title}</h1>"""
        f"""&nbsp;&nbsp;<span style="background:{badge_color};color:white;border-radius:6px;"""
        f"""padding:4px 10px;font-size:0.8rem;font-weight:600;vertical-align:middle;">"""
        f"""{safe_badge}</span>""",
        unsafe_allow_html=True,
    )
    st.caption(f"Lead: {appt.get('lead_name', 'N/A')} | By: {appt.get('user_name', 'N/A')}")
    st.markdown("---")

    new_title = st.text_input("Title", value=appt["title"], key=f"apt_title_{appt_id}")

    start_dt = datetime.fromisoformat(appt["start_time"].replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(appt["end_time"].replace("Z", "+00:00"))

    col_d, col_t = st.columns(2)
    with col_d:
        new_day = st.date_input("Date", value=start_dt.date(), key=f"apt_date_{appt_id}")
    with col_t:
        new_start_time = st.time_input("Start Time", value=start_dt.time(), key=f"apt_start_{appt_id}")

    new_end_time = st.time_input("End Time", value=end_dt.time(), key=f"apt_end_{appt_id}")

    mode_options = ["online", "in_person"]
    current_mode = appt.get("mode", "online")
    new_mode = st.selectbox("Mode", mode_options,
                            index=mode_options.index(current_mode) if current_mode in mode_options else 0,
                            format_func=lambda x: "Online" if x == "online" else "In Person",
                            key=f"apt_mode_{appt_id}")
    new_location = st.text_input("Location", value=appt.get("location") or "", key=f"apt_loc_{appt_id}")
    new_note = st.text_area("Note", value=appt.get("note") or "", height=80, key=f"apt_note_{appt_id}")

    # ── Mark as Completed checkbox (only for non-completed appointments) ─
    mark_completed = False
    if current_status != "completed":
        mark_completed = st.checkbox(
            "Mark as Completed",
            value=False,
            key=f"apt_complete_{appt_id}",
            help="Tick this and click Save to close out this appointment.",
        )

    col_save, col_del = st.columns(2)
    with col_save:
        if st.button("Save Changes", use_container_width=True, type="primary", key=f"apt_save_{appt_id}"):
            new_start_dt = datetime.combine(new_day, new_start_time)
            new_end_dt = datetime.combine(new_day, new_end_time)
            if new_end_dt <= new_start_dt:
                new_end_dt = new_start_dt + timedelta(hours=1)
            payload = {
                "title": new_title.strip() or appt["title"],
                "mode": new_mode,
                "location": new_location.strip() or None,
                "note": new_note.strip() or None,
                "start_time": new_start_dt.isoformat(),
                "end_time": new_end_dt.isoformat(),
            }
            if mark_completed:
                payload["status"] = "completed"
            try:
                api_client.update_appointment(state.token, appt_id, payload)
                st.toast("Appointment updated!" if not mark_completed else "Appointment marked as completed!")
                st.rerun()
            except APIError as e:
                st.error(f"Update failed: {e}")
    with col_del:
        if st.button("Delete", use_container_width=True, key=f"apt_del_{appt_id}"):
            try:
                api_client.delete_appointment(state.token, appt_id)
                st.toast("Appointment deleted.")
                st.rerun()
            except APIError as e:
                st.error(f"Delete failed: {e}")


# ── Create Lead Dialog ───────────────────────────────────────────────
@st.dialog("Create New Lead", width="medium")
def create_lead_dialog() -> None:
    """Dialog for creating a new lead.

    - Sales reps: the lead is auto-assigned to themselves (no rep dropdown).
    - Admins/Managers: a dropdown lets them pick which sales rep to assign.
    """
    user = state.user or {}
    user_role = user.get("role", "sales_rep")
    token = state.token

    with st.form("create_lead_form", clear_on_submit=True):
        name = st.text_input("Lead Name *", placeholder="e.g. Ramesh Sharma")

        col1, col2 = st.columns(2)
        with col1:
            profession = st.text_input("Profession *", placeholder="e.g. Business Owner")
        with col2:
            email = st.text_input("Email *", placeholder="e.g. ramesh@example.com")

        col3, col4 = st.columns(2)
        with col3:
            phone = st.text_input("Phone Number *", placeholder="e.g. 9876543210")
        with col4:
            # Lead source dropdown
            try:
                sources = api_client.get_sources(token)
                source_options = {s["id"]: s["name"] for s in sources}
                source_options_list = list(source_options.keys())
                source_id = st.selectbox(
                    "Lead Source",
                    options=[None] + source_options_list,
                    format_func=lambda x: "Select Source" if x is None else source_options[x],
                )
            except APIError:
                source_id = None
                st.caption("Could not load sources.")

        address = st.text_input("Address", placeholder="e.g. Panaji, Goa")
        note = st.text_area("Initial Note", placeholder="e.g. Met at trade show, interested in investment options...", height=80)

        # Assign-to dropdown: only for admin/manager
        assigned_rep_id = None
        if user_role in ("admin", "manager"):
            try:
                all_users = api_client.get_users(token)
                reps = [u for u in all_users if u["role"] == "sales_rep"]
                rep_options = {u["id"]: u["name"] for u in reps}
                rep_options_list = list(rep_options.keys())
                assigned_rep_id = st.selectbox(
                    "Assign to Sales Rep",
                    options=[None] + rep_options_list,
                    format_func=lambda x: "Unassigned" if x is None else rep_options[x],
                )
            except APIError:
                st.caption("Could not load sales reps.")

        submitted = st.form_submit_button("Create Lead", use_container_width=True, type="primary")
        if submitted:
            if not name.strip():
                st.error("Lead name is required.")
                return
            if not profession.strip():
                st.error("Profession is required.")
                return
            if not email.strip():
                st.error("Email is required.")
                return
            if not phone.strip():
                st.error("Phone number is required.")
                return

            data = {
                "name": name.strip(),
                "profession": profession.strip(),
                "email": email.strip(),
                "phone_number": phone.strip(),
            }
            if address and address.strip():
                data["address"] = address.strip()
            if note and note.strip():
                data["note"] = note.strip()
            if source_id is not None:
                data["source_id"] = source_id

            # Auto-assign for sales reps
            if user_role == "sales_rep":
                data["assigned_rep_id"] = user.get("id")
            elif assigned_rep_id is not None:
                data["assigned_rep_id"] = assigned_rep_id

            try:
                new_lead = api_client.create_lead(token, data)
                if new_lead and isinstance(new_lead, dict) and "id" in new_lead:
                    st.session_state[f"ai_refresh_pending_{new_lead['id']}"] = time.time()
                st.toast("Lead created successfully!")
                st.rerun()
            except APIError as e:
                st.error(f"Failed to create lead: {e}")


@st.dialog("Edit Lead", width="medium")
def edit_lead_dialog(lead: dict) -> None:
    """Dialog for editing an existing lead (admins only)."""
    token = state.token
    
    with st.form("edit_lead_form", clear_on_submit=False):
        name = st.text_input("Lead Name *", value=lead.get("name", ""))
        
        col1, col2 = st.columns(2)
        with col1:
            profession = st.text_input("Profession *", value=lead.get("profession") or "")
        with col2:
            email = st.text_input("Email *", value=lead.get("email") or "")
            
        col3, col4 = st.columns(2)
        with col3:
            phone = st.text_input("Phone Number *", value=lead.get("phone_number") or "")
        with col4:
            try:
                sources = api_client.get_sources(token)
                source_options = {s["id"]: s["name"] for s in sources}
                source_options_list = list(source_options.keys())
                
                # pre-select current source
                current_source = lead.get("source_id")
                default_index = 0
                if current_source in source_options_list:
                    default_index = source_options_list.index(current_source) + 1
                    
                source_id = st.selectbox(
                    "Lead Source",
                    options=[None] + source_options_list,
                    index=default_index,
                    format_func=lambda x: "Select Source" if x is None else source_options[x],
                )
            except Exception:
                source_id = lead.get("source_id")
                st.caption("Could not load sources.")
                
        address = st.text_input("Address", value=lead.get("address") or "")
        
        submitted = st.form_submit_button("Save Changes", use_container_width=True, type="primary")
        if submitted:
            if not name.strip() or not profession.strip() or not email.strip() or not phone.strip():
                st.error("Name, Profession, Email, and Phone are required.")
                return
                
            data = {
                "name": name.strip(),
                "profession": profession.strip(),
                "email": email.strip(),
                "phone_number": phone.strip(),
                "address": address.strip() if address else None,
                "source_id": source_id,
            }
            try:
                api_client.update_lead(token, lead["id"], data)
                st.toast("Lead updated successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to update lead: {e}")


@st.dialog(" ")
def manage_user_dialog(token: str, user=None):
    """Dialog for creating or editing a user.

    Moved from 1_Dashboard.py to be reusable across pages.

    Args:
        token: JWT auth token for API calls.
        user: Optional dict of existing user data for editing.
              Pass None to create a new user.
    """
    st.markdown(f"<h2>{'Edit User' if user else 'Create User'}</h2>", unsafe_allow_html=True)
    with st.form("manage_user_form"):
        name = st.text_input("Name*", value=user['name'] if user else "")
        email = st.text_input("Email*", value=user['email'] if user else "")
        phone_number = st.text_input("Phone Number*", value=user.get('phone_number') or "" if user else "")
        password = st.text_input(
            "Password (leave blank to keep current)" if user else "Password *",
            type="password",
        )
        role = st.selectbox(
            "Role",
            ["sales_rep", "manager", "admin"],
            index=["sales_rep", "manager", "admin"].index(user['role']) if user else 0,
        )

        try:
            all_users = api_client.get_users(token)
            managers = [u for u in all_users if u['role'] in ['manager', 'admin']]
            manager_options = {u['id']: u['name'] for u in managers}
            manager_options[None] = "None"
            current_manager = user.get('manager_id') if user else None
            manager_id = st.selectbox(
                "Manager",
                options=list(manager_options.keys()),
                format_func=lambda x: manager_options[x],
                index=(
                    list(manager_options.keys()).index(current_manager)
                    if current_manager in manager_options
                    else list(manager_options.keys()).index(None)
                ),
            )
        except APIError:
            manager_id = None

        submitted = st.form_submit_button("Save User")
        if submitted:
            if not name.strip() or not email.strip() or not phone_number.strip():
                st.error("Name, Email, and Phone Number cannot be empty.")
                return
            if not user and not password:
                st.error("Password is required when creating a new user.")
                return

            data = {
                "name": name.strip(),
                "email": email.strip(),
                "phone_number": phone_number.strip(),
                "role": role,
            }
            if manager_id is not None:
                data["manager_id"] = manager_id
            if password:
                data["password"] = password

            try:
                if user:
                    api_client.update_user(token, user['id'], data)
                    st.toast("User updated.")
                else:
                    api_client.register_user(token, data)
                    st.toast("User created.")
                st.rerun()
            except APIError as e:
                st.error(f"Error: {e}")
