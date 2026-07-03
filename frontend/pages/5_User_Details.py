import streamlit as st
from datetime import datetime
from core.auth import require_login
from core import api_client
from core.state import state
from core.api_client import APIError
from core.styles import inject_global_styles
from components.cards import render_lead_cards, render_task_cards, render_appointment_cards
from components.modals import show_lead_panel, show_task_panel, show_appointment_panel, metric_card

st.set_page_config(page_title="User Details", page_icon="👤", layout="wide")

inject_global_styles(drawer=True, overlay_cards=True, metric_card=True)

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

if st.button("← Back to Dashboard"):
    st.switch_page("pages/1_Dashboard.py")

st.title(f"Profile: {selected_user['name']}")
st.caption(f"{selected_user['role'].replace('_', ' ').title()} — {selected_user['email']}")

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
        render_lead_cards(active_leads, key_prefix="prof_active", on_click=show_lead_panel)
    else:
        st.info("No active leads assigned to this user.")

with tab2:
    if converted_leads:
        render_lead_cards(converted_leads, key_prefix="prof_conv", on_click=show_lead_panel)
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
