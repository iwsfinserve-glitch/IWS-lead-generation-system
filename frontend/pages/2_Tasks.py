import streamlit as st
import uuid
from datetime import datetime, date

st.set_page_config(page_title="Tasks", page_icon="", layout="wide")

# ── Page-level CSS: dotted background, drawer, overlay cards ──
st.markdown("""
<style>
.stApp {
    background-color: #fefefe;
    background-image:
        radial-gradient(circle, rgba(20,20,20,0.1) .8px, transparent .3px);
    background-size: 10px 10px;
}
/* Drawer backdrop */
div[data-testid="stModal"] > div:first-child {
    background: rgba(0, 0, 0, 0.5) !important;
    backdrop-filter: blur(4px);
}
/* Drawer position */
div[data-testid="stModal"] div[role="dialog"] {
    position: fixed !important;
    right: 0 !important; top: 0 !important; left: auto !important;
    width: 420px !important; max-width: 420px !important;
    height: 100vh !important; max-height: 100vh !important;
    border-radius: 0 !important; margin: 0 !important;
    transform: none !important; padding: 24px !important;
}
/* Overlay button on cards */
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

# ── Defensive state init (in case user navigates here directly) ──
if "tasks" not in st.session_state:
    st.session_state.tasks = [
        {"id": "T-001", "title": "Prepare Q3 proposal", "description": "Draft the proposal for Meridian Solutions."},
        {"id": "T-002", "title": "Update CRM records", "description": "Sync all lead statuses from this week."},
        {"id": "T-003", "title": "Schedule team standup", "description": "Book a recurring 15-min daily standup."},
    ]


# ── Dialogs ──
@st.dialog(" ", width="medium")
def create_task_dialog():
    st.markdown(f"""<h1 style="display: inline; font-weight: 800;">Create New Task</h1>""", unsafe_allow_html=True)
    title = st.text_input("Title", placeholder="e.g. Follow up with client")
    description = st.text_area("Description", height=120, placeholder="Description...")
    due_date = st.date_input("Due Date", value=date.today())
    

    if st.button("Create Task", use_container_width=True, type="primary"):
        if title.strip():
            st.session_state.tasks.append({
                "id": f"T-{uuid.uuid4().hex[:4].upper()}",
                "title": title.strip(),
                "description": description.strip(),
                "created": datetime.now().strftime("%Y-%m-%d"),
                "due": due_date.strftime("%Y-%m-%d"),
                "status": "New",
            })
            st.toast("Task created!")
            st.rerun()
        else:
            st.warning("Title is required.")


@st.dialog(" ", width="medium")
def task_detail_dialog(task_id):
    task = next((t for t in st.session_state.tasks if t["id"] == task_id), None)
    st.markdown(f"""<h1 style="display: inline; font-weight: 800;">{task['title']}</h1>""", unsafe_allow_html=True)
    st.markdown(f"""<div style="margin-top:4px; ">
                    <span style="color:#444; font-size:.9rem; font-weight:500; line-height:1.2;">
                        Created: {task['created']} | 
                    </span>
                    <span style="color:red; font-size:.9rem; font-weight:500; line-height:1.2;">
                        Due: {task['due']}
                    </span>
                </div>""", unsafe_allow_html=True)
    if not task:
        st.error("Task not found.")
        return
    st.markdown("---")

    # Editable fields
    col_due, col_status = st.columns(2)
    with col_due:
        new_due_date = st.date_input("Due Date", value=task["due"])
    with col_status:
        status_options = ["New", "In Progress", "Completed", "Overdue"]
        new_status = st.selectbox("Status", status_options,index=status_options.index(task.get("status", "New")))
    new_title = st.text_input("Title", value=task["title"])
    new_desc = st.text_area("Description", value=task["description"], height=150)

    col_update, col_delete = st.columns(2)
    with col_update:
        if st.button("Save Changes", use_container_width=True, type="primary"):
            task["title"] = new_title.strip() or task["title"]
            task["description"] = new_desc.strip()
            task["status"] = new_status
            task["due"] = new_due_date.strftime("%Y-%m-%d")
            st.toast("Task updated!")
            st.rerun()
    with col_delete:
        if st.button("Delete Task", use_container_width=True):
            st.session_state.tasks = [t for t in st.session_state.tasks if t["id"] != task_id]
            st.toast("Task deleted.")
            st.rerun()


# ── Page Header ──
st.title("Tasks")
st.markdown('<hr style="height:1px;background:#d4d4d4; margin-bottom: 10px; margin-top: 0px;">', unsafe_allow_html=True)

# ── Create button ──
if st.button("＋ New Task", type="primary"):
    create_task_dialog()

st.caption(f"{len(st.session_state.tasks)} tasks")

# ── Task Cards 
status_config = {
        "New":           {"abbr": "N",  "bg": "blue"},
        "In Progress":   {"abbr": "IP", "bg": "#FFC107"},
        "Completed":     {"abbr": "C",  "bg": "#4CAF50"},
        "Overdue":     {"abbr": "O",  "bg": "red"},
    }
for task in st.session_state.tasks:
    s = status_config.get(task['status'], {"abbr": "N",  "bg": "blue"})
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
                        Created: {task['created']} | 
                    </span>
                    <span style="color:red; font-size:.9rem; font-weight:500; line-height:1.2;">
                        Due: {task['due']}
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

    # Invisible overlay button — opens detail dialog
    if st.button("Select", key=f"task_card_{task['id']}", use_container_width=True):
        task_detail_dialog(task["id"])
