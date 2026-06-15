import streamlit as st
import uuid
import calendar
from datetime import datetime, date
from components.sidebar import render_sidebar

st.set_page_config(page_title="Appointments", page_icon="", layout="wide")
# render_sidebar()

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

# ── Defensive state init ──
if "appointments" not in st.session_state:
    st.session_state.appointments = [
        {"id": "A-001", "title": "Follow-up with Arjun", "day": "2026-06-10",
         "time": "10:00", "mode": "Online", "location": "Google Meet", "note": "Discuss pricing"},
        {"id": "A-002", "title": "Demo for Priya", "day": "2026-06-10",
         "time": "14:30", "mode": "In Person", "location": "GreenLeaf Office, Panaji",
         "note": "Product walkthrough"},
        {"id": "A-003", "title": "Contract review - Rohan", "day": "2026-06-12",
         "time": "11:00", "mode": "Online", "location": "Zoom", "note": "Final terms"},
    ]

if "cal_year" not in st.session_state:
    st.session_state.cal_year = datetime.now().year
if "cal_month" not in st.session_state:
    st.session_state.cal_month = datetime.now().month


# ── Dialogs ──
@st.dialog("New Appointment", width="medium")
def create_appointment_dialog(prefill_date=None):
    st.markdown("### Schedule Appointment")
    title = st.text_input("Title", placeholder="e.g. Call with client")
    col_d, col_t = st.columns(2)
    with col_d:
        day = st.date_input("Date", value=prefill_date or datetime.now().date())
    with col_t:
        time = st.time_input("Time")

    mode = st.selectbox("Mode", ["Online", "In Person"])
    location = st.text_input("Location", placeholder="e.g. Google Meet / Office address")
    note = st.text_area("Note", height=80, placeholder="Agenda or details...")

    if st.button("Create Appointment", use_container_width=True, type="primary"):
        if title.strip():
            st.session_state.appointments.append({
                "id": f"A-{uuid.uuid4().hex[:4].upper()}",
                "title": title.strip(),
                "day": day.strftime("%Y-%m-%d"),
                "time": time.strftime("%H:%M"),
                "mode": mode,
                "location": location.strip(),
                "note": note.strip(),
            })
            st.rerun()
        else:
            st.warning("Title is required.")


@st.dialog(" ", width="medium")
def appointment_detail_dialog(appt_id):
    appt = next((a for a in st.session_state.appointments if a["id"] == appt_id), None)
    if not appt:
        st.error("Appointment not found.")
        return
    st.markdown(f"""<h1 style="display: inline; font-weight: 800;">{appt['title']}</h1>""", unsafe_allow_html=True)
    st.markdown("---")

    new_title = st.text_input("Title", value=appt["title"])
    col_d, col_t = st.columns(2)
    with col_d:
        new_day = st.date_input("Date", value=datetime.strptime(appt["day"], "%Y-%m-%d").date())
    with col_t:
        h, m = appt["time"].split(":")
        from datetime import time as dt_time
        new_time = st.time_input("Time", value=dt_time(int(h), int(m)))

    new_mode = st.selectbox("Mode", ["Online", "In Person"],
                            index=0 if appt["mode"] == "Online" else 1)
    new_location = st.text_input("Location", value=appt["location"])
    new_note = st.text_area("Note", value=appt["note"], height=80)

    col_save, col_del = st.columns(2)
    with col_save:
        if st.button("Save Changes", use_container_width=True, type="primary"):
            appt["title"] = new_title.strip() or appt["title"]
            appt["day"] = new_day.strftime("%Y-%m-%d")
            appt["time"] = new_time.strftime("%H:%M")
            appt["mode"] = new_mode
            appt["location"] = new_location.strip()
            appt["note"] = new_note.strip()
            st.toast("Appointment updated!")
            st.rerun()
    with col_del:
        if st.button("Delete", use_container_width=True):
            st.session_state.appointments = [
                a for a in st.session_state.appointments if a["id"] != appt_id
            ]
            st.toast("Appointment deleted.")
            st.rerun()


@st.dialog(" ", width="medium")
def day_dialog(day_str):
    st.markdown("<h2 style='font-weight:bold;'>Day Appointments</h2>", unsafe_allow_html=True)
    day_date = datetime.strptime(day_str, "%Y-%m-%d").date()
    st.markdown(f"### {day_date.strftime('%B %d, %Y')}")
    st.markdown("---")

    day_appts = [a for a in st.session_state.appointments if a["day"] == day_str]

    if day_appts:
        for appt in day_appts:
            mode_color = "blue" if appt["mode"] == "Online" else "#4CAF50"
            st.markdown(
                f"""<div class="overlay-trigger" style="border:1px solid #ddd; border-radius:6px; padding:12px; margin-bottom:8px; background:white; cursor:pointer;">
                    <strong>{appt['time']}</strong> — {appt['title']}<br>
                    <span style="background:{mode_color}; color:white; border-radius:4px;
                          padding:2px 6px; font-size:0.7rem; margin-left:8px;">{appt['mode']}</span>
                    <span style="color:#777; font-size:0.85rem;">Location: {appt['location']}</span>
                </div>""",
                unsafe_allow_html=True,
            )
            # Button to open detail dialog — closes day_dialog, reopens as detail
            if st.button(f"View {appt['title']}", key=f"day_view_{appt['id']}", use_container_width=True):
                st.session_state.pending_appt_id = appt["id"]
                st.rerun()
    else:
        st.caption("No appointments on this day.")

    st.markdown("---")
    st.markdown("**Quick Add**")
    quick_title = st.text_input("Title", placeholder="New appointment title", key=f"quick_{day_str}")
    quick_time = st.time_input("Time", key=f"quick_time_{day_str}")
    if st.button("Add to this day", use_container_width=True, type="primary", key=f"quick_btn_{day_str}"):
        if quick_title.strip():
            st.session_state.appointments.append({
                "id": f"A-{uuid.uuid4().hex[:4].upper()}",
                "title": quick_title.strip(),
                "day": day_str,
                "time": quick_time.strftime("%H:%M"),
                "mode": "Online",
                "location": "",
                "note": "",
            })
            st.rerun()


# ── Page Header ──
st.title("Appointments")
st.markdown('<hr style="height:1px;background:#d4d4d4; margin-bottom: 10px; margin-top: 0px;">', unsafe_allow_html=True)

# ── View Toggle ──
view = st.radio("View", ["Calendar View", "List View"], horizontal=True, label_visibility="collapsed")

# ── New Appointment button ──
if st.button("＋ New Appointment", type="primary"):
    create_appointment_dialog()

st.caption(f"{len(st.session_state.appointments)} appointments total")

# ── Auto-open detail dialog if redirected from calendar day view ──
if "pending_appt_id" in st.session_state and st.session_state.pending_appt_id:
    appt_id = st.session_state.pending_appt_id
    st.session_state.pending_appt_id = None  # Clear so it doesn't loop
    appointment_detail_dialog(appt_id)

# =====================================================
# LIST VIEW
# =====================================================
if view == "List View":
    # Sort by day then time
    sorted_appts = sorted(st.session_state.appointments, key=lambda a: (a["day"], a["time"]))

    for appt in sorted_appts:
        mode_color, text = ("blue", "ON") if appt["mode"] == "Online" else ("#4CAF50", "IP")
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
                            {appt['time']}
                        </span>
                    </div>
                    <div style="margin-top:4px;">
                        <span style="color:red; font-size:0.9rem; font-weight:500;">
                            Date: {appt['day']}
                        </span>
                        <span style="color:#777; font-size:0.9rem; font-weight:500;">
                           &nbsp;|&nbsp; Location: {appt['location'] or 'TBD'}
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
    for appt in st.session_state.appointments:
        if appt["day"].startswith(month_str):
            day_num = int(appt["day"].split("-")[2])
            appt_counts[day_num] = appt_counts.get(day_num, 0) + 1

    # Render calendar as HTML grid + Streamlit buttons for clickable days
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

                    # Style: highlight today, show dot for appointments
                    border = "2px solid blue" if is_today else "1px solid #ddd"
                    bg = "white" if is_today else "white"
                    txt = "white" if is_today else "#333"
                    dot = f"<span style='display:inline-block; background:blue; color:white; border-radius:50%; width:18px; height:18px; font-size:0.65rem; line-height:18px; text-align:center;'>{count}</span>" if count > 0 else ""
                    st.markdown("""
                        <style>
                            /* Pull the button up over the card using negative margin */
                            div.element-container:has(.overlay-trigger) {
                                margin-bottom: -85px;
                                position: relative;
                            }
                            /* Style the button container to be invisible but clickable */
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
                            /* Add a subtle hover effect to the HTML card */
                            .overlay-trigger:hover {
                                border-color: red !important;
                                background-color: white !important;
                                transform: translateY(-5px) !important;
                            }
                        </style>
                        """, unsafe_allow_html=True)

                    # Construct the HTML on a single line under the hood, 
                    # but keep it readable in Python using parenthesis concatenation.
                    html_content = (
                        f"""<div onmouseover="this.style.color = 'red';" class="overlay-trigger" style='border:{border}; border-radius:6px; background:{bg}; """
                        f"padding:8px; text-align:center; min-height:100px; margin-bottom:4px; transition: transform 0.15 ease;'>"
                        f"<span  style='font-weight:600; color:#333;'>{day_num}</span><br>{dot}"
                        f"</div>" )

                    st.markdown(html_content, unsafe_allow_html=True)

                    # Clickable button for each day
                    day_str = f"{year}-{month:02d}-{day_num:02d}"
                    if st.button("View", key=f"cal_{day_str}", use_container_width=True):
                        day_dialog(day_str)

