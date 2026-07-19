import streamlit as st
from datetime import datetime, date
from core.auth import require_login
from core import api_client
from core.api_client import APIError
from core.state import state
from core.styles import inject_global_styles
from components.layout import render_sidebar, render_pagination, render_divider
from components.cards import render_task_cards, render_request_cards
from components.modals import show_task_panel

st.set_page_config(page_title="Tasks", page_icon="", layout="wide")

inject_global_styles(drawer=True, overlay_cards=True)


# ── Create Task Dialog (Manager/Admin — assign to any user) ──────────
@st.dialog(" ", width="medium")
def create_task_dialog():
    st.markdown(f"""<h1 style="display: inline; font-weight: 800;">Create New Task</h1>""", unsafe_allow_html=True)
    title = st.text_input("Title", placeholder="e.g. Follow up with client")
    description = st.text_area("Description", height=120, placeholder="Description...")
    due_date = st.date_input("Due Date", value=date.today())

    user_options = st.session_state.get("user_options", {})
    if user_options:
        user_id = st.selectbox("Assign To", options=list(user_options.keys()),
                               format_func=lambda x: user_options.get(x, str(x)))
    else:
        user_id = state.user.get("id") if state.user else None
        st.info(f"Assigning to: {state.user.get('name', 'You') if state.user else 'Unknown'}")

    if st.button("Create Task", use_container_width=True, type="primary"):
        if title.strip():
            try:
                api_client.create_task(state.token, {
                    "user_id": user_id,
                    "title": title.strip(),
                    "notes": description.strip() or None,
                    "due": due_date.isoformat(),
                })
                st.toast("Task created!")
            except APIError as e:
                st.error(f"Failed to create task: {e}")
        else:
            st.warning("Title is required.")


# ── Create Self-Assigned Task Dialog (Sales Rep) ─────────────────────
@st.dialog(" ", width="medium")
def create_self_task_dialog():
    st.markdown(f"""<h1 style="display: inline; font-weight: 800;">Create Task</h1>""", unsafe_allow_html=True)
    st.caption("This task will be assigned to you.")
    title = st.text_input("Title", placeholder="e.g. Prepare client proposal", key="self_task_title")
    description = st.text_area("Description", height=120, placeholder="Description...", key="self_task_desc")
    due_date = st.date_input("Due Date", value=date.today(), key="self_task_due")

    if st.button("Create Task", use_container_width=True, type="primary", key="self_task_submit"):
        if title.strip():
            try:
                api_client.create_self_task(state.token, {
                    "title": title.strip(),
                    "notes": description.strip() or None,
                    "due": due_date.isoformat(),
                })
                st.toast("Task created!")
            except APIError as e:
                st.error(f"Failed to create task: {e}")
        else:
            st.warning("Title is required.")


require_login()

TOKEN = state.token
USER = state.user or {}
USER_ROLE = USER.get("role", "sales_rep")

# ── Sidebar ──
render_sidebar(key_suffix="task")

# ── Init pagination state ──
if "pending_task_page" not in st.session_state:
    st.session_state.pending_task_page = 1
if "completed_task_page" not in st.session_state:
    st.session_state.completed_task_page = 1

PAGE_SIZE = 10

# ── Fetch all tasks ──
try:
    all_tasks = api_client.get_tasks(TOKEN, limit=1000)
except APIError as e:
    st.error(f"Failed to load tasks: {e}")
    all_tasks = []

# Fetch users for the "assign to" dropdown (admin/manager only)
users_list = []
if USER_ROLE in ("admin", "manager"):
    try:
        users_list = api_client.get_users(TOKEN)
    except APIError:
        users_list = []

user_options = {u["id"]: f"{u['name']} ({u['role']})" for u in users_list}
st.session_state.user_options = user_options

# ── Page Header ──
st.title("Tasks")
render_divider()

# ── Create button ──
# Admin/Manager: can assign to anyone; Sales Rep: self-assign only
if USER_ROLE in ("admin", "manager"):
    if st.button("New Task", type="primary"):
        create_task_dialog()
else:
    if st.button("New Task", type="primary"):
        create_self_task_dialog()

# ── Split into pending vs completed ──
pending_tasks = [t for t in all_tasks if t.get("status") != "completed"]
completed_tasks = [t for t in all_tasks if t.get("status") == "completed"]

# ── Tabs ─────────────────────────────────────────────────────────────
# Build tabs: always show Pending + Completed, add Due Date Requests for managers
tab_labels = [
    f"Pending ({len(pending_tasks)})",
    f"Completed ({len(completed_tasks)})",
]

# Fetch due date requests for managers
due_date_requests = []
if USER_ROLE in ("admin", "manager"):
    try:
        due_date_requests = api_client.get_due_date_requests(TOKEN)
    except APIError:
        due_date_requests = []

    pending_requests = [r for r in due_date_requests if r.get("status") == "pending"]
    tab_labels.append(f"Due Date Requests ({len(pending_requests)})")

tabs = st.tabs(tab_labels)

# ── Pending Tasks Tab ────────────────────────────────────────────────
with tabs[0]:
    skip = (st.session_state.pending_task_page - 1) * PAGE_SIZE
    page_tasks = pending_tasks[skip : skip + PAGE_SIZE]
    st.caption(f"Showing {len(page_tasks)} of {len(pending_tasks)} pending tasks")
    if page_tasks:
        render_task_cards(page_tasks, key_prefix="pending_task_card", on_click=show_task_panel)
        render_pagination(len(pending_tasks), "pending_task_page", page_size=PAGE_SIZE)
    else:
        st.info("No pending tasks found.")

# ── Completed Tasks Tab ──────────────────────────────────────────────
with tabs[1]:
    skip = (st.session_state.completed_task_page - 1) * PAGE_SIZE
    page_tasks = completed_tasks[skip : skip + PAGE_SIZE]
    st.caption(f"Showing {len(page_tasks)} of {len(completed_tasks)} completed tasks")
    if page_tasks:
        render_task_cards(page_tasks, key_prefix="completed_task_card", on_click=show_task_panel)
        render_pagination(len(completed_tasks), "completed_task_page", page_size=PAGE_SIZE)
    else:
        st.info("No completed tasks found.")

# ── Due Date Requests Tab (Manager/Admin only) ──────────────────────
if USER_ROLE in ("admin", "manager") and len(tabs) > 2:
    with tabs[2]:
        pending_reqs = [r for r in due_date_requests if r.get("status") == "pending"]
        resolved_reqs = [r for r in due_date_requests if r.get("status") != "pending"]

        if not pending_reqs and not resolved_reqs:
            st.info("No due date change requests.")
        else:
            # ── Pending Requests ──────────────────────────────────────
            if pending_reqs:
                st.subheader(f"Pending Requests ({len(pending_reqs)})")

                def _approve_due_date(req_id):
                    try:
                        api_client.update_due_date_request(TOKEN, req_id, {"status": "approved"})
                        st.toast("Request approved!")
                        st.rerun()
                    except APIError as e:
                        st.error(f"Failed: {e}")

                def _reject_due_date(req_id):
                    try:
                        api_client.update_due_date_request(TOKEN, req_id, {"status": "rejected"})
                        st.toast("Request rejected.")
                        st.rerun()
                    except APIError as e:
                        st.error(f"Failed: {e}")

                render_request_cards(
                    pending_reqs,
                    key_prefix="dd",
                    title_field="task_title",
                    subtitle_fn=lambda r: (
                        f"<b>Requested by:</b> {r.get('requested_by_name', 'N/A')} &nbsp;|&nbsp;"
                        f"<b>New date:</b> <span style='color:red; font-weight:500;'>{r.get('requested_date', 'N/A')}</span>"
                    ),
                    detail_fn=lambda r: f'"{r.get("reason", "")}"',
                    on_approve=_approve_due_date,
                    on_reject=_reject_due_date,
                )

            # ── Resolved Requests ─────────────────────────────────────
            if resolved_reqs:
                with st.expander(f"Resolved Requests ({len(resolved_reqs)})", expanded=False):
                    for req in resolved_reqs:
                        status_label = "Approved" if req.get("status") == "approved" else "Rejected"
                        st.markdown(f"""
                            **{req.get('task_title', 'Unknown')}** - {status_label}
                            \n Requested by {req.get('requested_by_name', 'N/A')} for {req.get('requested_date', 'N/A')}
                            - *"{req.get('reason', '')}"*
                        """)
                        st.markdown("---")
