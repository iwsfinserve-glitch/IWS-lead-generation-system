import streamlit as st
import asyncio
from datetime import datetime, date
from core.auth import require_login, logout
from core import api_client
from core.api_client import APIError
from core.state import state
from core.styles import inject_global_styles
from components.layout import render_sidebar
from components.cards import render_task_cards
from components.modals import show_task_panel

st.set_page_config(page_title="Tasks", page_icon="", layout="wide")

inject_global_styles(drawer=True, overlay_cards=True)


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




require_login()

TOKEN = state.token
USER = state.user or {}

# ── Sidebar ──
render_sidebar(key_suffix="task")

# ── Pagination Setup ──
if "task_page" not in st.session_state:
    st.session_state.task_page = 1

PAGE_SIZE = 25

# ── Fetch data ──
skip = (st.session_state.task_page - 1) * PAGE_SIZE
try:
    # For simplicity, we just fetch the current page. 
    # In a real app we'd want total_count from backend for pagination limits.
    # We will fetch PAGE_SIZE + 1 to know if there's a next page.
    fetched_tasks = api_client.get_tasks(TOKEN, skip=skip, limit=PAGE_SIZE + 1)
    
    has_next = len(fetched_tasks) > PAGE_SIZE
    page_tasks = fetched_tasks[:PAGE_SIZE]
    st.session_state.page_tasks = page_tasks
except APIError as e:
    st.error(f"Failed to load tasks: {e}")
    page_tasks = []
    has_next = False
    st.session_state.page_tasks = []

# Fetch users for the "assign to" dropdown (admin/manager only)
users_list = []
if USER.get("role") in ("admin", "manager"):
    try:
        users_list = api_client.get_users(TOKEN)
    except APIError:
        users_list = []

user_options = {u["id"]: f"{u['name']} ({u['role']})" for u in users_list}
st.session_state.user_options = user_options

# ── Page Header ──
st.title("Tasks")
st.markdown('<hr style="height:1px;background:#d4d4d4; margin-bottom: 10px; margin-top: 0px;">', unsafe_allow_html=True)

# ── Create button (admin/manager only) ──
if USER.get("role") in ("admin", "manager"):
    if st.button("＋ New Task", type="primary"):
        create_task_dialog()

st.caption(f"Showing tasks (Page {st.session_state.task_page})")

@st.fragment
def render_tasks(page_tasks, has_next):
    # ── Task Cards ──
    render_task_cards(page_tasks, key_prefix="task_card", on_click=show_task_panel)

    # Pagination controls
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c1:
        if st.session_state.task_page > 1:
            if st.button("← Previous", use_container_width=True):
                st.session_state.task_page -= 1
    with c3:
        if has_next:
            if st.button("Next →", use_container_width=True):
                st.session_state.task_page += 1

render_tasks(page_tasks, has_next)
