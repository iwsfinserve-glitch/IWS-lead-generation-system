"""
modals.py — Shared modal dialog components.

Extracts the lead detail drawer panel that was previously copy-pasted
between 1_Dashboard.py and 6_All_Leads.py.  Both pages now import
show_lead_panel() from here.

Usage:
    from components.modals import show_lead_panel
    show_lead_panel(lead_id, status_color)
"""

import streamlit as st
from datetime import datetime, date, timedelta
from core import api_client
from core.state import state
from core.api_client import APIError


# ── Shared Constants ─────────────────────────────────────────────────
STATUS_DISPLAY = {
    "new": "New",
    "in_progress": "In Progress",
    "potential": "Potential",
    "non_potential": "Non-Potential",
    "converted_to_investor": "Converted",
}

STATUS_OPTIONS_API = ["new", "in_progress", "potential", "non_potential", "converted_to_investor"]
STATUS_OPTIONS_DISPLAY = [STATUS_DISPLAY[s] for s in STATUS_OPTIONS_API]

STATUS_CONFIG = {
    "new":           {"abbr": "N",  "bg": "blue"},
    "in_progress":   {"abbr": "IP", "bg": "#FFC107"},
    "potential":     {"abbr": "P",  "bg": "#4CAF50"},
    "non_potential": {"abbr": "NP", "bg": "Red"},
    "converted_to_investor": {"abbr": "C", "bg": "#2196F3"},
}

ACTIVE_STATUSES = {"new", "in_progress", "potential", "non_potential"}


# ── Helper Widgets ───────────────────────────────────────────────────
def status_span(status_type: str, bg_color: str) -> str:
    """Return an HTML badge span for a lead status."""
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
        {status_type}
    </span>
    """


def metric_card(label: str, value) -> str:
    """Return an HTML metric card for dashboard summary grids."""
    return f'<div style="border: 1px solid rgba(54,57,62,0.3); border-radius: 8px; padding: 20px; text-align: center; background-color: white;"><p style="color: #888; font-size: 0.85rem; margin: 0 0 8px 0; text-transform: uppercase; letter-spacing: 1px;">{label}</p><p style="color: red; font-size: 2.2rem; font-weight: 700; margin: 0;">{value}</p></div>'


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

    st.markdown(f"""<h1 style="display: inline; font-weight: 800;">{lead["name"]}</h1>&nbsp;&nbsp;<h4 style="display: inline; font-weight: 400;">{lead.get("profession") or ""}</h4>""", unsafe_allow_html=True)
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

    # Check permissions: only assigned rep can update lead details
    user_id = (state.user or {}).get("id")
    can_update = (user_id is not None) and (str(lead.get("assigned_rep_id")) == str(user_id))

    if can_update:
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

    st.markdown("---")

    # Interaction History
    st.markdown("<h2>Interaction History</h2>", unsafe_allow_html=True)
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
                    st.markdown(f"**{ts}** — `{old} → {new}`\n\n_{note_text}_" if note_text else f"**{ts}** — `{old} → {new}`")
                elif event_type == "note":
                    st.markdown(f"**{ts}** — _{meta.get('note', '')}_")
                elif event_type == "lead_created":
                    st.markdown(f"**{ts}** — Lead created from {meta.get('source', 'unknown source')}")
                elif event_type == "appointment_booked":
                    st.markdown(f"**{ts}** — Appointment: {meta.get('title', '')}")
                else:
                    st.markdown(f"**{ts}** — {event_type}")
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

    st.markdown(f"""<h1 style="display: inline; font-weight: 800;">{task['title']}</h1>""", unsafe_allow_html=True)

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
        new_due_date = st.date_input("Due Date", value=due_val, key=f"tsk_due_{task_id}")
    with col_status:
        status_options = ["needsAction", "completed"]
        status_display = {"needsAction": "Pending", "completed": "Completed"}
        current_status = task.get("status", "needsAction")
        new_status = st.selectbox("Status",
                                  options=status_options,
                                  index=status_options.index(current_status) if current_status in status_options else 0,
                                  format_func=lambda x: status_display.get(x, x),
                                  key=f"tsk_status_{task_id}")

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

    st.markdown(f"""<h1 style="display: inline; font-weight: 800;">{appt['title']}</h1>""", unsafe_allow_html=True)
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

    col_save, col_del = st.columns(2)
    with col_save:
        if st.button("Save Changes", use_container_width=True, type="primary", key=f"apt_save_{appt_id}"):
            new_start_dt = datetime.combine(new_day, new_start_time)
            new_end_dt = datetime.combine(new_day, new_end_time)
            if new_end_dt <= new_start_dt:
                new_end_dt = new_start_dt + timedelta(hours=1)
            try:
                api_client.update_appointment(state.token, appt_id, {
                    "title": new_title.strip() or appt["title"],
                    "mode": new_mode,
                    "location": new_location.strip() or None,
                    "note": new_note.strip() or None,
                    "start_time": new_start_dt.isoformat(),
                    "end_time": new_end_dt.isoformat(),
                })
                st.toast("Appointment updated!")
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

