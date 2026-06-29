import streamlit as st
import calendar
from datetime import datetime, date, timedelta
from components.auth_guard import require_login
import api_client

st.set_page_config(page_title="Appointments", page_icon="", layout="wide")

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
    margin-bottom: -75px; position: relative;
}
div.element-container:has(.overlay-trigger) + div.element-container {
    opacity: 0; position: relative; z-index: 10;
}
div.element-container:has(.overlay-trigger) + div.element-container button {
    height: 75px !important; width: 100% !important; cursor: pointer;
}
.overlay-trigger:hover {
    border-color: #555 !important; background-color: #f9f9f9 !important;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar ──
with st.sidebar:
    st.markdown(f"**{USER.get('name', '')}**")
    st.caption(f"{USER.get('role', '').replace('_', ' ').title()}")
    if st.button("Logout", use_container_width=True, key="appt_logout"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# ── Fetch data ──
try:
    appointments = api_client.get_appointments(TOKEN)
except Exception as e:
    st.error(f"Failed to load appointments: {e}")
    appointments = []

try:
    leads = api_client.get_leads(TOKEN)
    lead_options = {l["id"]: f"{l['name']} (ID: {l['id']})" for l in leads}
except Exception:
    leads = []
    lead_options = {}

if "cal_year" not in st.session_state:
    st.session_state.cal_year = datetime.now().year
if "cal_month" not in st.session_state:
    st.session_state.cal_month = datetime.now().month


# ── Dialogs ──
@st.dialog("New Appointment", width="medium")
def create_appointment_dialog(prefill_date=None):
    st.markdown("### Schedule Appointment")
    lead_id = st.selectbox("Lead", options=list(lead_options.keys()),
                           format_func=lambda x: lead_options.get(x, str(x)))
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
                api_client.create_appointment(TOKEN, {
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
            except Exception as e:
                st.error(f"Failed to create appointment: {e}")
        else:
            st.warning("Title and Lead are required.")


@st.dialog(" ", width="medium")
def appointment_detail_dialog(appt_id):
    appt = next((a for a in appointments if a["id"] == appt_id), None)
    if not appt:
        st.error("Appointment not found.")
        return
    st.markdown(f"""<h1 style="display: inline; font-weight: 800;">{appt['title']}</h1>""", unsafe_allow_html=True)
    st.caption(f"Lead: {appt.get('lead_name', 'N/A')} | By: {appt.get('user_name', 'N/A')}")
    st.markdown("---")

    new_title = st.text_input("Title", value=appt["title"])

    start_dt = datetime.fromisoformat(appt["start_time"].replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(appt["end_time"].replace("Z", "+00:00"))

    col_d, col_t = st.columns(2)
    with col_d:
        new_day = st.date_input("Date", value=start_dt.date())
    with col_t:
        new_start_time = st.time_input("Start Time", value=start_dt.time(), key=f"det_start_{appt_id}")

    new_end_time = st.time_input("End Time", value=end_dt.time(), key=f"det_end_{appt_id}")

    mode_options = ["online", "in_person"]
    current_mode = appt.get("mode", "online")
    new_mode = st.selectbox("Mode", mode_options,
                            index=mode_options.index(current_mode) if current_mode in mode_options else 0,
                            format_func=lambda x: "Online" if x == "online" else "In Person")
    new_location = st.text_input("Location", value=appt.get("location") or "")
    new_note = st.text_area("Note", value=appt.get("note") or "", height=80)

    col_save, col_del = st.columns(2)
    with col_save:
        if st.button("Save Changes", use_container_width=True, type="primary"):
            new_start_dt = datetime.combine(new_day, new_start_time)
            new_end_dt = datetime.combine(new_day, new_end_time)
            if new_end_dt <= new_start_dt:
                new_end_dt = new_start_dt + timedelta(hours=1)
            try:
                api_client.update_appointment(TOKEN, appt_id, {
                    "title": new_title.strip() or appt["title"],
                    "mode": new_mode,
                    "location": new_location.strip() or None,
                    "note": new_note.strip() or None,
                    "start_time": new_start_dt.isoformat(),
                    "end_time": new_end_dt.isoformat(),
                })
                st.toast("Appointment updated!")
                st.rerun()
            except Exception as e:
                st.error(f"Update failed: {e}")
    with col_del:
        if st.button("Delete", use_container_width=True):
            try:
                api_client.delete_appointment(TOKEN, appt_id)
                st.toast("Appointment deleted.")
                st.rerun()
            except Exception as e:
                st.error(f"Delete failed: {e}")


@st.dialog(" ", width="medium")
def day_dialog(day_str):
    st.markdown("<h2 style='font-weight:bold;'>Day Appointments</h2>", unsafe_allow_html=True)
    day_date = datetime.strptime(day_str, "%Y-%m-%d").date()
    st.markdown(f"### {day_date.strftime('%B %d, %Y')}")
    st.markdown("---")

    day_appts = [a for a in appointments if a["start_time"][:10] == day_str]

    if day_appts:
        for appt in day_appts:
            time_str = appt["start_time"][11:16]
            mode_color = "blue" if appt.get("mode") == "online" else "#4CAF50"
            mode_label = "Online" if appt.get("mode") == "online" else "In Person"
            st.markdown(
                f"""<div class="overlay-trigger" style="border:1px solid #ddd; border-radius:6px; padding:12px; margin-bottom:8px; background:white; cursor:pointer;">
                    <strong>{time_str}</strong> — {appt['title']}<br>
                    <span style="background:{mode_color}; color:white; border-radius:4px;
                          padding:2px 6px; font-size:0.7rem; margin-left:8px;">{mode_label}</span>
                    <span style="color:#777; font-size:0.85rem;">Lead: {appt.get('lead_name', 'N/A')}</span>
                </div>""",
                unsafe_allow_html=True,
            )
            if st.button(f"View {appt['title']}", key=f"day_view_{appt['id']}", use_container_width=True):
                st.session_state.pending_appt_id = appt["id"]
                st.rerun()
    else:
        st.caption("No appointments on this day.")


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
    appointment_detail_dialog(appt_id)

# =====================================================
# LIST VIEW
# =====================================================
if view == "List View":
    sorted_appts = sorted(appointments, key=lambda a: a["start_time"])

    for appt in sorted_appts:
        mode = appt.get("mode", "online")
        mode_color, text = ("blue", "ON") if mode == "online" else ("#4CAF50", "IP")
        day_str = appt["start_time"][:10]
        time_str = appt["start_time"][11:16]

        st.markdown(
            f"""
            <div class="overlay-trigger" style="
                display: flex;
                border: 1px solid rgba(54,57,62,0.3);
                border-radius: 6px;
                margin-bottom: 12px;
                overflow: hidden;
                height: 75px;
                transition: all 0.2s;
                background: white;
            ">
                <div style="flex:1; padding:12px 16px;">
                    <div style="display:flex; align-items:baseline; justify-content:space-between;">
                        <span style="color:#333; font-size:1.1rem; font-weight:600; line-height:1.2;">
                            {appt['title']}
                        </span>
                        <span style="color:#555; font-size:0.85rem; font-weight:500;">
                            {time_str}
                        </span>
                    </div>
                    <div style="margin-top:4px;">
                        <span style="color:red; font-size:0.9rem; font-weight:500;">
                            Date: {day_str}
                        </span>
                        <span style="color:#777; font-size:0.9rem; font-weight:500;">
                           &nbsp;|&nbsp; Lead: {appt.get('lead_name', 'N/A')} &nbsp;|&nbsp; {appt.get('location') or 'TBD'}
                        </span>
                    </div>
                </div>
                <div style="
                    display:flex; align-items:center; justify-content:center;
                    background:{mode_color}; min-width:70px; padding:0 12px;
                ">
                    <span style="color:white; font-size:0.75rem; font-weight:600;">
                        {text}
                    </span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("Select", key=f"appt_card_{appt['id']}", use_container_width=True):
            appointment_detail_dialog(appt["id"])

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

                    st.markdown("""
                        <style>
                            div.element-container:has(.overlay-trigger) {
                                margin-bottom: -85px;
                                position: relative;
                            }
                            div.element-container:has(.overlay-trigger) + div.element-container {
                                opacity: 0;
                                position: relative;
                                z-index: 10;
                            }
                            div.element-container:has(.overlay-trigger) + div.element-container button {
                                height: 75px !important;
                                width: 100% !important;
                                cursor: pointer;
                            }
                            .overlay-trigger:hover {
                                border-color: red !important;
                                background-color: white !important;
                                transform: translateY(-5px) !important;
                            }
                        </style>
                        """, unsafe_allow_html=True)

                    html_content = (
                        f"""<div onmouseover="this.style.color = 'red';" class="overlay-trigger" style='border:{border}; border-radius:6px; background:white; """
                        f"padding:8px; text-align:center; min-height:100px; margin-bottom:4px; transition: transform 0.15 ease;'>"
                        f"<span  style='font-weight:600; color:#333;'>{day_num}</span><br>{dot}"
                        f"</div>" )

                    st.markdown(html_content, unsafe_allow_html=True)

                    day_str = f"{year}-{month:02d}-{day_num:02d}"
                    if st.button("View", key=f"cal_{day_str}", use_container_width=True):
                        day_dialog(day_str)
