import streamlit as st
import asyncio
from datetime import datetime
from core.auth import require_login, logout
from core import api_client
from core.state import state
from core.api_client import APIError
from core.styles import inject_global_styles
from components.layout import render_sidebar, render_pagination, render_divider
from components.modals import (
    metric_card, STATUS_DISPLAY, create_lead_dialog,
    show_appointment_panel, show_task_panel, manage_user_dialog,
)
from components.cards import render_lead_card, render_lead_cards, render_user_cards, render_appointment_cards, render_task_cards

st.set_page_config(
    page_title="Lead Management System",
    page_icon="",
    layout="wide"
)

inject_global_styles(drawer=True, overlay_cards=True, user_cards=True)


def navigate_to_lead(lead_id: int, status_color: str = "") -> None:
    """Navigate to the dedicated Lead Details page."""
    st.session_state.selected_lead_id = lead_id
    st.session_state.lead_details_origin = "pages/1_Dashboard.py"
    st.switch_page("pages/7_Lead_Details.py")


require_login()

TOKEN = state.token
USER = state.user or {}

# ── Sidebar: User info + Logout ──
render_sidebar(key_suffix="dash")

# ── Page Header ──
user_name = USER.get("name", "")
st.title(f"Welcome, {user_name}" if user_name else "Welcome")
render_divider()
st.markdown('<h2 style="margin-bottom: 10px;">Dashboard</h2>', unsafe_allow_html=True)

# ── Pagination Setup ──
if "lead_page" not in st.session_state:
    st.session_state.lead_page = 1

PAGE_SIZE = 25

def get_leads_data():
    try:
        user_id = (state.user or {}).get("id")
        user_role = (state.user or {}).get("role")
        rep_id = user_id if user_role == "sales_rep" else None
        all_leads = api_client.get_leads(TOKEN, assigned_rep_id=rep_id, limit=1000)
        skip = (st.session_state.lead_page - 1) * PAGE_SIZE
        page_leads = all_leads[skip : skip + PAGE_SIZE]
        return all_leads, page_leads
    except APIError as e:
        st.error(f"Failed to load leads: {e}")
        return [], []

@st.fragment
def render_sales_rep_dashboard():

    all_leads, page_leads = get_leads_data()
    total = len(all_leads)
    new = len([l for l in all_leads if l["status"] == "new"])
    potent = len([l for l in all_leads if l["status"] == "potential"])
    converted = len([l for l in all_leads if l["status"] == "converted_to_investor"])

    st.markdown(
        f"""
<div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:16px; margin-bottom:20px;">
{metric_card("Total Leads", total)}
{metric_card("New Leads", new)}
{metric_card("Potential Leads", potent)}
{metric_card("Converted", converted)}
</div>
        """,
        unsafe_allow_html=True,
    )
    render_filters_and_leads(all_leads, show_rep_filter=False)

    # ── Upcoming Appointments & Pending Tasks side-by-side ──
    st.markdown("<br>", unsafe_allow_html=True)
    col_appts, col_tasks = st.columns(2)

    with col_appts:
        st.subheader("Upcoming Appointments")
        render_divider()

        try:
            appts = api_client.get_appointments(TOKEN)
            from datetime import datetime as dt
            now = dt.now().isoformat()
            upcoming = sorted(
                [a for a in appts if a["start_time"] >= now],
                key=lambda a: a["start_time"],
            )[:5]
            if upcoming:
                render_appointment_cards(upcoming, key_prefix="dash_appt", on_click=show_appointment_panel)
            else:
                st.caption("No upcoming appointments.")
        except APIError as e:
            st.error(f"Failed to load appointments: {e}")

    with col_tasks:
        st.subheader("Pending Tasks")
        render_divider()

        try:
            tasks = api_client.get_tasks(TOKEN, limit=100)
            pending = [t for t in tasks if t.get("status") == "needsAction"][:5]
            if pending:
                render_task_cards(pending, key_prefix="dash_task", on_click=show_task_panel)
            else:
                st.caption("No pending tasks.")
        except APIError as e:
            st.error(f"Failed to load tasks: {e}")

# ── Filters ──
@st.fragment
def render_filters_and_leads(all_leads, show_rep_filter=True):
    st.subheader("All Leads")
    render_divider()

    rep_filter = []
    source_names = sorted(set(l.get("source_name", "") for l in all_leads if l.get("source_name")))
    if show_rep_filter:
        # Get unique assigned reps from the leads data
        rep_names = sorted(set(l.get("assigned_rep_name", "") for l in all_leads if l.get("assigned_rep_name")))
        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
        with filter_col1:
            status_filter = st.multiselect(
                "Status Filter",
                options=list(STATUS_DISPLAY.values()),
            )
        with filter_col2:
            source_filter = st.multiselect(
                "Filter by Source",
                options=source_names,
            )
        with filter_col3:
            rep_filter = st.multiselect(
                "Filter by rep",
                options=rep_names,
            )
        with filter_col4:
            search_term = st.text_input("Search by Name", value="", placeholder="Enter Name here")
    else:
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        with filter_col1:
            status_filter = st.multiselect(
                "Status Filter",
                options=list(STATUS_DISPLAY.values()),
            )
        with filter_col2:
            source_filter = st.multiselect(
                "Filter by Source",
                options=source_names,
            )
        with filter_col3:
            search_term = st.text_input("Search by Name", value="", placeholder="Enter Name here")

    filtered_leads = all_leads
    if status_filter:
        api_statuses = [k for k, v in STATUS_DISPLAY.items() if v in status_filter]
        filtered_leads = [l for l in filtered_leads if l["status"] in api_statuses]
    if source_filter:
        filtered_leads = [l for l in filtered_leads if l.get("source_name") in source_filter]
    if rep_filter:
        filtered_leads = [l for l in filtered_leads if l.get("assigned_rep_name") in rep_filter]
    if search_term:
        term = search_term.lower()
        filtered_leads = [l for l in filtered_leads if term in l["name"].lower() or term in (l.get("profession") or "").lower()]

    # Client-side pagination slice
    PAGE_SIZE = 10
    skip = (st.session_state.lead_page - 1) * PAGE_SIZE
    paginated_filtered_leads = filtered_leads[skip:skip+PAGE_SIZE]

    total_pages = (len(filtered_leads) // PAGE_SIZE) + (1 if len(filtered_leads) % PAGE_SIZE > 0 else 0)

    st.caption(f"Showing {len(paginated_filtered_leads)} of {len(filtered_leads)} leads (Page {st.session_state.lead_page} of {total_pages})")
    if st.button("Create New Lead", type="primary"):
        create_lead_dialog()

    render_lead_cards(paginated_filtered_leads, key_prefix="card", on_click=navigate_to_lead)
            
    # render_pagination(len(filtered_leads), "lead_page", page_size=10)


def delete_user_handler(user_id):
    try:
        api_client.delete_user(TOKEN, user_id)
        st.toast("User deleted.")
        st.rerun()
    except APIError as e:
        st.error(f"Failed to delete: {e}")

def manage_user_dialog_wrapper(user=None):
    """Wrapper to pass the TOKEN to the shared manage_user_dialog."""
    manage_user_dialog(TOKEN, user)

def render_manager_dashboard():
    try:
        users = api_client.get_users(TOKEN)
        # Filter reps that report to this manager
        my_reps = [u for u in users if u.get("manager_id") == USER.get("id")]
        
        st.markdown(
            f"""
<div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:16px; margin-bottom:20px;">
{metric_card("Direct Reports", len(my_reps))}
</div>
            """, unsafe_allow_html=True
        )
        st.subheader(f"Sales Representatives ({len(my_reps)})")
        render_user_cards(my_reps, key_prefix="mgr_user", is_admin=False)
    except APIError as e:
        st.error(f"Failed to fetch users: {e}")

def render_admin_dashboard():
    if st.button("Create New User", type="primary"):
        manage_user_dialog_wrapper()
    try:
        users = api_client.get_users(TOKEN)
        
        st.markdown(
            f"""
<div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:16px; margin-bottom:20px;">
{metric_card("Total Users", len(users))}
{metric_card("Admins", len([u for u in users if u['role'] == 'admin']))}
{metric_card("Managers", len([u for u in users if u['role'] == 'manager']))}
{metric_card("Sales Reps", len([u for u in users if u['role'] == 'sales_rep']))}
</div>
            """, unsafe_allow_html=True
        )
        st.subheader(f"Directory ({len(users)})")
        render_user_cards(
            users,
            key_prefix="adm_user",
            is_admin=True,
            on_edit=manage_user_dialog_wrapper,
            on_delete=delete_user_handler,
        )
    except APIError as e:
        st.error(f"Failed to fetch users: {e}")


# ── Role-based Rendering ──
user_role = USER.get('role', 'sales_rep')
if user_role == 'admin':
    render_admin_dashboard()
elif user_role == 'manager':
    render_manager_dashboard()
else:
    render_sales_rep_dashboard()
