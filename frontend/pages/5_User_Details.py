import html
import streamlit as st
from datetime import datetime
from core.auth import require_login
from core import api_client
from core.state import state
from core.api_client import APIError
from core.styles import inject_global_styles
from components.cards import render_lead_cards, render_task_cards, render_appointment_cards
from components.modals import show_task_panel, show_appointment_panel, metric_card, manage_user_dialog

st.set_page_config(page_title="User Details", page_icon="", layout="wide")

inject_global_styles(overlay_cards=True, metric_card=True)


def navigate_to_lead(lead_id: int, status_color: str = "") -> None:
    """Navigate to the dedicated Lead Details page."""
    st.session_state.selected_lead_id = lead_id
    st.session_state.lead_details_origin = "pages/5_User_Details.py"
    st.switch_page("pages/7_Lead_Details.py")

require_login()

if "selected_user_id" not in st.session_state or not st.session_state.selected_user_id:
    st.warning("No user selected.")
    if st.button("← Back to Dashboard"):
        st.switch_page("pages/1_Dashboard.py")
    st.stop()

selected_user_id = st.session_state.selected_user_id

try:
    # We can fetch all users and filter, or just fetch all and find the one.
    users = api_client.get_users(state.token)
    selected_user = next((u for u in users if u["id"] == selected_user_id), None)
    if not selected_user:
        st.error("User not found.")
        st.stop()
        
    assigned_leads = api_client.get_leads(state.token, assigned_rep_id=selected_user_id, limit=500)
    assigned_tasks = api_client.get_tasks(state.token, user_id=selected_user_id, limit=500)
    user_appts = api_client.get_appointments(state.token, user_id=selected_user_id)
    st.session_state.assigned_tasks = assigned_tasks
    st.session_state.user_appts = user_appts
    
except APIError as e:
    st.error(f"Failed to fetch data: {e}")
    st.stop()

if st.button("← Back to Dashboard", type="primary"):
    st.switch_page("pages/1_Dashboard.py")

st.title("User Profile")

safe_name = html.escape(str(selected_user.get('name') or 'N/A'))
safe_role = html.escape(str((selected_user.get('role') or 'sales_rep').replace('_', ' ').title()))
safe_email = html.escape(str(selected_user.get('email') or 'N/A'))
safe_phone = html.escape(str(selected_user.get('phone_number') or 'N/A'))

# We can lookup manager name if available. But typically manager_id is returned.
manager_id = selected_user.get("manager_id")
manager_name = "None"
if manager_id:
    manager_match = next((u for u in users if u["id"] == manager_id), None)
    if manager_match:
        manager_name = manager_match.get("name", f"ID: {manager_id}")
safe_manager_name = html.escape(str(manager_name))
        
st.markdown(
    f"""
    <div style="background:white; border:1px solid #ddd; border-radius:8px; padding:20px; margin-bottom:20px;">
        <h2 style="margin-top:0; color:#333; margin-bottom:8px; display:inline-block;">{safe_name}</h2>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:16px;">
            <div>
                <span style="color:#666; font-size:0.85rem; font-weight:600; text-transform:uppercase;">Email</span><br>
                <span style="color:#333; font-size:1.05rem;">{safe_email}</span>
            </div>
            <div>
                <span style="color:#666; font-size:0.85rem; font-weight:600; text-transform:uppercase;">Phone Number</span><br>
                <span style="color:#333; font-size:1.05rem;">{safe_phone}</span>
            </div>
            <div>
                <span style="color:#666; font-size:0.85rem; font-weight:600; text-transform:uppercase;">Role</span><br>
                <span style="color:#333; font-size:1.05rem;">{safe_role}</span>
            </div>
            <div>
                <span style="color:#666; font-size:0.85rem; font-weight:600; text-transform:uppercase;">Reports To</span><br>
                <span style="color:#333; font-size:1.05rem;">{safe_manager_name}</span>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

if state.user and state.user.get("role") == "admin":
    empty_col, edit_col = st.columns([2,2])
    with edit_col:
        col_edit, col_del = st.columns(2)
        with col_edit:
            if st.button("Edit Details", use_container_width=True, key="admin_edit_user"):
                manage_user_dialog(state.token, selected_user)
        with col_del:
            if st.button("Delete User", type="primary", use_container_width=True, key="admin_del_user"):
                st.session_state[f"confirm_del_user_{selected_user_id}"] = True
                    
        if st.session_state.get(f"confirm_del_user_{selected_user_id}", False):
            st.warning(f"Are you sure you want to permanently delete user '{safe_name}'? This cannot be undone.")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("Yes, Delete", type="primary", use_container_width=True, key="admin_del_user_yes"):
                    try:
                        api_client.delete_user(state.token, selected_user_id)
                        st.toast("User deleted successfully.")
                        st.session_state[f"confirm_del_user_{selected_user_id}"] = False
                        st.switch_page("pages/1_Dashboard.py")
                    except Exception as e:
                        st.error(f"Failed to delete: {e}")
            with col_no:
                if st.button("Cancel", use_container_width=True, key="admin_del_user_no"):
                    st.session_state[f"confirm_del_user_{selected_user_id}"] = False
                    st.rerun()


active_leads = [l for l in assigned_leads if l["status"] != "converted_to_investor"]
converted_leads = [l for l in assigned_leads if l["status"] == "converted_to_investor"]

st.markdown(
    f'<div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:16px; margin-bottom:20px;">{metric_card("Active Leads", len(active_leads))}{metric_card("Converted Leads", len(converted_leads))}{metric_card("Pending Tasks", len([t for t in assigned_tasks if t.get("status") == "needsAction"]))}{metric_card("Upcoming Appts", len(user_appts))}</div>',
    unsafe_allow_html=True,
)

tab1, tab2, tab3, tab4 = st.tabs([
    f"Active Leads ({len(active_leads)})",
    f"Converted Leads ({len(converted_leads)})",
    f"Tasks ({len(assigned_tasks)})",
    f"Appointments ({len(user_appts)})",
])

with tab1:
    if active_leads:
        render_lead_cards(active_leads, key_prefix="prof_active", on_click=navigate_to_lead)
    else:
        st.info("No active leads assigned to this user.")

with tab2:
    if converted_leads:
        render_lead_cards(converted_leads, key_prefix="prof_conv", on_click=navigate_to_lead)
    else:
        st.info("No converted leads assigned to this user.")

with tab3:
    if assigned_tasks:
        render_task_cards(assigned_tasks, key_prefix="prof_task", on_click=show_task_panel)
    else:
        st.info("No tasks assigned to this user.")

with tab4:
    if user_appts:
        render_appointment_cards(user_appts, key_prefix="prof_appt", on_click=show_appointment_panel)
    else:
        st.info("No upcoming appointments for this user.")
