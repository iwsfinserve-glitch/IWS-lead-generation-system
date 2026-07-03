import streamlit as st
import asyncio
import calendar
from datetime import datetime, date, timedelta
from core.auth import require_login, logout
from core import api_client
from core.api_client import APIError
from core.state import state
from core.styles import inject_global_styles
from components.layout import render_sidebar
from components.cards import render_appointment_cards
from components.modals import show_appointment_panel

st.set_page_config(page_title="Appointments", page_icon="", layout="wide")

inject_global_styles(drawer=True, overlay_cards=True)


@st.dialog("New Appointment", width="medium")
def create_appointment_dialog(prefill_date=None):
    st.markdown("### Schedule Appointment")
    lead_id = st.selectbox("Lead", options=list(st.session_state.lead_options.keys()),
                           format_func=lambda x: st.session_state.lead_options.get(x, str(x)))
    title = st.text_input("Title", placeholder="e.g. Call with client")
    col_d, col_t = st.columns(2)
    with col_d:
        day = st.date_input("Date", value=prefill_date or datetime.now().date())
    with col_t:
        start_time = st.time_input("Start Time", key="new_start")
    end_time = st.time_input("End Time", key="new_end")

    mode = st.selectbox("Mode", ["online", "in_person"], format_func=lambda x: "Online" if x == "online" else "In Person")
    location = st.text_input("Location", placeholder="e.g. Google Meet / Office address")
    note = st.text_area("Note", height=80, placeholder="Agenda or details...")

    if st.button("Create Appointment", use_container_width=True, type="primary"):
        if title.strip() and lead_id:
            start_dt = datetime.combine(day, start_time)
            end_dt = datetime.combine(day, end_time)
            if end_dt <= start_dt:
                end_dt = start_dt + timedelta(hours=1)

            try:
                api_client.create_appointment(state.token, {
                    "lead_id": lead_id,
                    "title": title.strip(),
                    "note": note.strip() or None,
                    "mode": mode,
                    "location": location.strip() or None,
                    "start_time": start_dt.isoformat(),
                    "end_time": end_dt.isoformat(),
                })
                st.toast("Appointment created!")
                st.rerun()
            except APIError as e:
                st.error(f"Failed to create appointment: {e}")
        else:
            st.warning("Title and Lead are required.")


@st.dialog(" ", width="medium")
def day_dialog(day_str):
    st.markdown("<h2 style='font-weight:bold;'>Day Appointments</h2>", unsafe_allow_html=True)
    day_date = datetime.strptime(day_str, "%Y-%m-%d").date()
    st.markdown(f"### {day_date.strftime('%B %d, %Y')}")
    st.markdown("---")

    day_appts = [a for a in st.session_state.appointments if a["start_time"][:10] == day_str]

    if day_appts:
        import bleach
        for appt in day_appts:
            time_str = appt["start_time"][11:16]
            mode_color = "blue" if appt.get("mode") == "online" else "#4CAF50"
            mode_label = "Online" if appt.get("mode") == "online" else "In Person"
            safe_title = bleach.clean(appt['title'])
            safe_lead = bleach.clean(appt.get('lead_name') or 'N/A')
            
            st.markdown(
                f"""<div class="overlay-trigger" style="border:1px solid #ddd; border-radius:6px; padding:12px; margin-bottom:8px; background:white; cursor:pointer;">
                    <strong>{time_str}</strong> — {safe_title}<br>
                    <span style="background:{mode_color}; color:white; border-radius:4px;
                          padding:2px 6px; font-size:0.7rem; margin-left:8px;">{mode_label}</span>
                    <span style="color:#777; font-size:0.85rem;">Lead: {safe_lead}</span>
                </div>""",
                unsafe_allow_html=True,
            )
            if st.button(f"View {appt['title']}", key=f"day_view_{appt['id']}", use_container_width=True):
                st.session_state.pending_appt_id = appt["id"]
                st.rerun()
    else:
        st.caption("No appointments on this day.")


require_login()

TOKEN = state.token
USER = state.user or {}

# ── Sidebar ──
render_sidebar(key_suffix="appt")

# ── Fetch data ──
try:
    appointments = api_client.get_appointments(TOKEN)
    st.session_state.appointments = appointments
except APIError as e:
    st.error(f"Failed to load appointments: {e}")
    appointments = []
    st.session_state.appointments = []

try:
    leads = api_client.get_leads(TOKEN)
    lead_options = {l["id"]: f"{l['name']} (ID: {l['id']})" for l in leads}
    st.session_state.lead_options = lead_options
except APIError:
    lead_options = {}
    st.session_state.lead_options = {}

if "cal_year" not in st.session_state:
    st.session_state.cal_year = datetime.now().year
if "cal_month" not in st.session_state:
    st.session_state.cal_month = datetime.now().month

# ── Page Header ──
st.title("Appointments")
st.markdown('<hr style="height:1px;background:#d4d4d4; margin-bottom: 10px; margin-top: 0px;">', unsafe_allow_html=True)

# ── View Toggle ──
view = st.radio("View", ["Calendar View", "List View"], horizontal=True, label_visibility="collapsed")

# ── New Appointment button ──
if st.button("＋ New Appointment", type="primary"):
    create_appointment_dialog()

st.caption(f"{len(appointments)} appointments total")

# ── Auto-open detail dialog if redirected from calendar day view ──
if "pending_appt_id" in st.session_state and st.session_state.pending_appt_id:
    appt_id = st.session_state.pending_appt_id
    st.session_state.pending_appt_id = None
    show_appointment_panel(appt_id)

# =====================================================
# LIST VIEW
# =====================================================
if view == "List View":
    sorted_appts = sorted(appointments, key=lambda a: a["start_time"])

    render_appointment_cards(sorted_appts, key_prefix="appt_card", on_click=show_appointment_panel)

# =====================================================
# CALENDAR VIEW
# =====================================================
elif view == "Calendar View":
    year = st.session_state.cal_year
    month = st.session_state.cal_month

    # Month navigation
    nav_left, nav_center, nav_right = st.columns([1, 3, 1])
    with nav_left:
        if st.button("◀", use_container_width=True):
            if month == 1:
                st.session_state.cal_month = 12
                st.session_state.cal_year = year - 1
            else:
                st.session_state.cal_month = month - 1
            st.rerun()
    with nav_center:
        st.markdown(
            f"<h3 style='text-align:center; margin:0; color:black;'>{calendar.month_name[month]} {year}</h3>",
            unsafe_allow_html=True,
        )
    with nav_right:
        if st.button("▶", use_container_width=True):
            if month == 12:
                st.session_state.cal_month = 1
                st.session_state.cal_year = year + 1
            else:
                st.session_state.cal_month = month + 1
            st.rerun()

    # Build appointment count per day for this month
    month_str = f"{year}-{month:02d}"
    appt_counts = {}
    for appt in appointments:
        appt_day = appt["start_time"][:10]
        if appt_day.startswith(month_str):
            day_num = int(appt_day.split("-")[2])
            appt_counts[day_num] = appt_counts.get(day_num, 0) + 1

    # Calendar grid
    weeks = calendar.monthcalendar(year, month)
    today = date.today()

    # Day headers
    day_cols = st.columns(7)
    for i, day_name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        day_cols[i].markdown(
            f"<p style='text-align:center; font-weight:600; color:red; margin-bottom:4px;'>{day_name}</p>",
            unsafe_allow_html=True,
        )

    # Week rows
    for week in weeks:
        cols = st.columns(7)
        for i, day_num in enumerate(week):
            with cols[i]:
                if day_num == 0:
                    st.markdown("&nbsp;", unsafe_allow_html=True)
                else:
                    count = appt_counts.get(day_num, 0)
                    is_today = (year == today.year and month == today.month and day_num == today.day)

                    border = "2px solid blue" if is_today else "1px solid #ddd"
                    dot = f"<span style='display:inline-block; background:blue; color:white; border-radius:50%; width:18px; height:18px; font-size:0.65rem; line-height:18px; text-align:center;'>{count}</span>" if count > 0 else ""



                    html_content = (
                        f"""<div onmouseover="this.style.color = 'red';" class="overlay-trigger" style='border:{border}; border-radius:6px; background:white; """
                        f"padding:8px; text-align:center; min-height:100px; margin-bottom:4px; transition: transform 0.15 ease;'>"
                        f"<span  style='font-weight:600; color:#333;'>{day_num}</span><br>{dot}"
                        f"</div>" )

                    st.markdown(html_content, unsafe_allow_html=True)

                    day_str = f"{year}-{month:02d}-{day_num:02d}"
                    if st.button("View", key=f"cal_{day_str}", use_container_width=True):
                        day_dialog(day_str)
