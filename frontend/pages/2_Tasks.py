import streamlit as st
from datetime import datetime, date
from components.auth_guard import require_login
import api_client

st.set_page_config(page_title="Tasks", page_icon="", layout="wide")

# ── Auth gate ──
require_login()

TOKEN = st.session_state.token
USER = st.session_state.user

# ── Page-level CSS ──
st.markdown("""
<style>
.stApp {
    background-color: #fefefe;
    background-image:
        radial-gradient(circle, rgba(20,20,20,0.1) .8px, transparent .3px);
    background-size: 10px 10px;
}
div[data-testid="stModal"] > div:first-child {
    background: rgba(0, 0, 0, 0.5) !important;
    backdrop-filter: blur(4px);
}
div[data-testid="stModal"] div[role="dialog"] {
    position: fixed !important;
    right: 0 !important; top: 0 !important; left: auto !important;
    width: 420px !important; max-width: 420px !important;
    height: 100vh !important; max-height: 100vh !important;
    border-radius: 0 !important; margin: 0 !important;
    transform: none !important; padding: 24px !important;
}
div.element-container:has(.overlay-trigger) {
    margin-bottom: -75px;
    position: relative;
}
div.element-container:has(.overlay-trigger) + div.element-container {
    opacity: 0; position: relative; z-index: 10;
}
div.element-container:has(.overlay-trigger) + div.element-container button {
    height: 65px !important; width: 100% !important; cursor: pointer;
}
.overlay-trigger:hover {
    border-color: #555 !important;
    background-color: #f9f9f9 !important;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar ──
with st.sidebar:
    st.markdown(f"**{USER.get('name', '')}**")
    st.caption(f"{USER.get('role', '').replace('_', ' ').title()}")
    if st.button("Logout", use_container_width=True, key="task_logout"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# ── Fetch data ──
try:
    tasks = api_client.get_tasks(TOKEN)
except Exception as e:
    st.error(f"Failed to load tasks: {e}")
    tasks = []

# Fetch users for the "assign to" dropdown (admin/manager only)
users_list = []
if USER.get("role") in ("admin", "manager"):
    try:
        users_list = api_client.get_users(TOKEN)
    except Exception:
        users_list = []

user_options = {u["id"]: f"{u['name']} ({u['role']})" for u in users_list}


# ── Dialogs ──
@st.dialog(" ", width="medium")
def create_task_dialog():
    st.markdown(f"""<h1 style="display: inline; font-weight: 800;">Create New Task</h1>""", unsafe_allow_html=True)
    title = st.text_input("Title", placeholder="e.g. Follow up with client")
    description = st.text_area("Description", height=120, placeholder="Description...")
    due_date = st.date_input("Due Date", value=date.today())

    if user_options:
        user_id = st.selectbox("Assign To", options=list(user_options.keys()),
                               format_func=lambda x: user_options.get(x, str(x)))
    else:
        user_id = USER.get("id")
        st.info(f"Assigning to: {USER.get('name', 'You')}")

    if st.button("Create Task", use_container_width=True, type="primary"):
        if title.strip():
            try:
                api_client.create_task(TOKEN, {
                    "user_id": user_id,
                    "title": title.strip(),
                    "notes": description.strip() or None,
                    "due": due_date.isoformat(),
                })
                st.toast("Task created!")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to create task: {e}")
        else:
            st.warning("Title is required.")


@st.dialog(" ", width="medium")
def task_detail_dialog(task_id):
    task = next((t for t in tasks if t["id"] == task_id), None)
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

    # Editable fields
    col_due, col_status = st.columns(2)
    with col_due:
        try:
            due_val = datetime.strptime(task["due"], "%Y-%m-%d").date() if task.get("due") else date.today()
        except:
            due_val = date.today()
        new_due_date = st.date_input("Due Date", value=due_val)
    with col_status:
        status_options = ["needsAction", "completed"]
        status_display = {"needsAction": "Pending", "completed": "Completed"}
        current_status = task.get("status", "needsAction")
        new_status = st.selectbox("Status",
                                  options=status_options,
                                  index=status_options.index(current_status) if current_status in status_options else 0,
                                  format_func=lambda x: status_display.get(x, x))

    new_title = st.text_input("Title", value=task["title"])
    new_desc = st.text_area("Notes", value=task.get("notes") or "", height=150)

    col_update, col_delete = st.columns(2)
    with col_update:
        if st.button("Save Changes", use_container_width=True, type="primary"):
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
                    api_client.update_task(TOKEN, task_id, update_data)
                    st.toast("Task updated!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Update failed: {e}")
            else:
                st.toast("No changes.")
    with col_delete:
        if st.button("Delete Task", use_container_width=True):
            try:
                api_client.delete_task(TOKEN, task_id)
                st.toast("Task deleted.")
                st.rerun()
            except Exception as e:
                st.error(f"Delete failed: {e}")


# ── Page Header ──
st.title("Tasks")
st.markdown('<hr style="height:1px;background:#d4d4d4; margin-bottom: 10px; margin-top: 0px;">', unsafe_allow_html=True)

# ── Create button (admin/manager only) ──
if USER.get("role") in ("admin", "manager"):
    if st.button("＋ New Task", type="primary"):
        create_task_dialog()

st.caption(f"{len(tasks)} tasks")

# ── Task Cards ──
status_config = {
    "needsAction": {"abbr": "P",  "bg": "#FFC107", "label": "Pending"},
    "completed":   {"abbr": "C",  "bg": "#4CAF50", "label": "Completed"},
}

for task in tasks:
    s = status_config.get(task.get("status", "needsAction"), {"abbr": "?", "bg": "#555", "label": "Unknown"})
    assigned_on = task.get("assigned_on", "")[:10]
    due = task.get("due") or "N/A"

    # Check if overdue
    is_overdue = False
    if task.get("due") and task.get("status") == "needsAction":
        try:
            if datetime.strptime(task["due"], "%Y-%m-%d").date() < date.today():
                is_overdue = True
                s = {"abbr": "O", "bg": "red", "label": "Overdue"}
        except:
            pass

    st.markdown(
        f"""
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
                        {task['title']}
                    </span>
                </div>
                <div style="margin-top:4px; ">
                    <span style="color:#777; font-size:.9rem; font-weight:500; line-height:1.2;">
                        Assigned to: {task.get('user_name', 'N/A')} |
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
        """,
        unsafe_allow_html=True,
    )

    if st.button("Select", key=f"task_card_{task['id']}", use_container_width=True):
        task_detail_dialog(task["id"])
