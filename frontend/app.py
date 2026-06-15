from streamlit.runtime.state.common import WidgetSerializer
import streamlit as st
import pandas as pd
from datetime import datetime
from components.sidebar import render_sidebar

st.set_page_config(
    page_title="Lead Management System",
    page_icon="",
    layout="wide"
)

# # # Sidebar   
# render_sidebar()
st.markdown("""
<style>
.stApp {
    background-color: #fefefe;
    background-image:
        radial-gradient(circle, rgba(20,20,20,0.1) .8px, transparent .3px);
    background-size: 10px 10px;
}
</style>
""", unsafe_allow_html=True)

# ── CSS: Make the dialog appear as a right-side drawer with blurred backdrop ──
st.markdown("""
<style>
    /* Blur + darken the backdrop behind the dialog */
    div[data-testid="stModal"] > div:first-child {
        background: rgba(0, 0, 0, 0.5) !important;
        backdrop-filter: blur(4px);
    }
    /* Reposition the dialog as a right-side drawer */
    div[data-testid="stModal"] div[role="dialog"] {
        position: fixed !important;
        right: 0 !important;
        top: 0 !important;
        left: auto !important;
        width: 420px !important;
        max-width: 420px !important;
        height: 100vh !important;
        max-height: 100vh !important;
        border-radius: 0 !important;
        margin: 0 !important;
        transform: none !important;
        padding: 24px !important;
    }
</style>
""", unsafe_allow_html=True)

# ── Lead Detail Drawer (using @st.dialog) ──
@st.dialog(" ", width="medium")
def show_lead_panel(lead_id, status_color):
    lead_mask = st.session_state.leads_df["Lead ID"] == lead_id
    lead_data = st.session_state.leads_df.loc[lead_mask].iloc[0]

    # Header: Name + Company (matching wireframe)
    # st.header(f"{lead_data['Name']}")
    # st.caption(lead_data["Company"])
    st.markdown(f"""<h1 style="display: inline; font-weight: 800;">{lead_data["Name"]}</h1>&nbsp;&nbsp;<h4 style="display: inline; font-weight: 400;">{lead_data["Company"]}</h4>""", unsafe_allow_html=True)
    st.markdown("---")

    # Details section
    st.markdown('<h2>Details</h2>', unsafe_allow_html=True)
    source_col, assignedTo_col = st.columns(2)
    with source_col: st.markdown(f"**Source:** {lead_data['Source']}")
    with assignedTo_col: st.markdown(f"**Assigned To:** {lead_data['Assigned To']}")
        
    email_col, phone_col = st.columns(2)
    with email_col: st.markdown(f"**Email:** {lead_data['Email']}")
    with phone_col: st.markdown(f"**Phone No:** {lead_data['Phone']}")
    
    lastContact_col, status_col = st.columns(2)
    with lastContact_col: st.markdown(f"**Last Contact:** {lead_data['Last Contact']}")
    with status_col: st.markdown(f"**Status:** {status_span(lead_data['Status'], status_color)}", unsafe_allow_html=True)
    
    st.markdown("---")

    # Update Lead section
    st.markdown('<h2>Update Lead</h2>', unsafe_allow_html=True)
    STATUS_OPTIONS = ["New", "In Progress", "Potential", "Non-Potential"]
    
    status_col, date_col = st.columns(2)
    with status_col:
        new_status = st.selectbox(
            "Change Status",
            options=STATUS_OPTIONS,
            index=STATUS_OPTIONS.index(lead_data["Status"]),
        )
    with date_col:
        try:
            current_date = datetime.strptime(lead_data["Last Contact"], "%Y-%m-%d").date()
        except:
            current_date = datetime.now().date()
        new_last_contact = st.date_input("Last Contact", value=current_date)
        
    if st.button("Update Lead Details", use_container_width=True, type="primary"):
        st.session_state.leads_df.loc[lead_mask, "Status"] = new_status
        st.session_state.leads_df.loc[lead_mask, "Last Contact"] = new_last_contact.strftime("%Y-%m-%d")
        
        # Log the status change
        if new_status != lead_data["Status"]:
            st.session_state.interaction_log.append({
                "lead_id": lead_id,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "note": "Status updated manually.",
                "status_change": f"{lead_data['Status']} → {new_status}"
            })
            
        st.toast("Lead details updated successfully!")
        st.rerun()

    st.markdown("---")
    
    # Appointment Booking Section (Future Google Calendar Integration)
    st.markdown('<h2>Book Appointment</h2>', unsafe_allow_html=True)
    appt_date_col, btn_col = st.columns([3, 1])
    with appt_date_col:
        appointment_date = st.date_input("Select Appointment Date", label_visibility="collapsed")
    with btn_col:
        if st.button("Select", key=f"book_appt_{lead_id}", use_container_width=True):
            st.toast(f"Feature coming soon: Book appointment on {appointment_date}")

    st.markdown("---")

    # Notes Section
    st.markdown("<h2>Interaction History</h2>", unsafe_allow_html=True)
    with st.form(key=f"note_form_{lead_id}", clear_on_submit=True):
        notes = st.text_area("Add a new note", height=100, placeholder="Enter call notes here...")
        submitted = st.form_submit_button("Add Note", use_container_width=True)
        if submitted and notes.strip():
            st.session_state.interaction_log.append({
                "lead_id": lead_id,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "note": notes.strip(),
                "status_change": ""
            })
            st.rerun()
            
    # Show Note History
    st.markdown("<br>", unsafe_allow_html=True)
    lead_logs = [log for log in st.session_state.interaction_log if log["lead_id"] == lead_id]
    if lead_logs:
        for log in reversed(lead_logs):
            status_text = f" — `{log['status_change']}`" if log.get('status_change') else ""
            st.markdown(
                f"**{log['timestamp']}**{status_text}\n\n"
                f"_{log['note']}_"
            )
            st.markdown("---")
    else:
        st.caption("No notes yet.")

def metric_card(label, value):
    return f"""
    <div style="
        border: 1px solid rgba(54,57,62,0.3);
        border-radius: 8px;
        padding: 20px;
        text-align: center;
        background-color: white;
    ">
        <p style="
            color: #888;
            font-size: 0.85rem;
            margin: 0 0 8px 0;
            text-transform: uppercase;
            letter-spacing: 1px;
        ">
            {label}
        </p>
        <p style="
            color: red;
            font-size: 2.2rem;
            font-weight: 700;
            margin: 0;
        ">
            {value}
        </p>
    </div>
    """
def status_span(status_type, bg_color):
    return f"""
    <span style="
    border-radius: 6px;
    padding: 4px 8px;
    background-color: {bg_color};
    color: white;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    ">
        {status_type}
    </span>
    """


if "leads_df" not in st.session_state:
    st.session_state.leads_df = pd.DataFrame({
        "Lead ID":    ["L-001", "L-002", "L-003", "L-004", "L-005"],
        "Name":       ["Arjun Mehta", "Priya Sharma", "Rohan Desai", "Sneha Nair", "Vikram Patel"],
        "Company":    ["TechNova Pvt Ltd", "GreenLeaf Exports", "Meridian Solutions", "Coastal Ventures", "Pinnacle Corp"],
        "Email":      ["arjun@technova.in", "priya@greenleaf.in", "rohan@meridian.in", "sneha@coastal.in", "vikram@pinnacle.in"],
        "Phone":      ["+91-9876543210", "+91-9123456780", "+91-9988776655", "+91-9012345678", "+91-9876012345"],
        "Status":     ["New", "In Progress", "Potential", "New", "Non-Potential"],
        "Source":     ["Website", "Referral", "Cold Call", "LinkedIn", "Website"],
        "Assigned To":["Amit", "Amit", "Suresh", "Neha", "Rahul"],
        "Last Contact": ["2026-06-01", "2026-06-03", "2026-05-28", "2026-06-04", "2026-05-20"],
    })

if "interaction_log" not in st.session_state:
    st.session_state.interaction_log = [
        {
            "lead_id": "L-001",
            "timestamp": "2026-06-05 10:30",
            "note": "Initial call. Client is interested in our new software suite. Requested a follow-up next week.",
            "status_change": "New → Potential"
        },
        {
            "lead_id": "L-002",
            "timestamp": "2026-06-03 14:15",
            "note": "Sent pricing details. Waiting for their response.",
            "status_change": "New → In Progress"
        }
    ]

if "selected_lead_id" not in st.session_state:
    st.session_state.selected_lead_id = None

# ── Appointments dummy data ──
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

# ── Tasks dummy data ──
if "tasks" not in st.session_state:
    st.session_state.tasks = [
        {"id": "T-001", "created": "2026-06-10", "due": "2026-06-15", "title": "Prepare Q3 proposal", "description": "Draft the proposal for Meridian Solutions.", "status":"New"},
        {"id": "T-002", "created": "2026-06-10", "due": "2026-06-15", "title": "Update CRM records", "description": "Sync all lead statuses from this week.", "status":"In Progress"},
        {"id": "T-003", "created": "2026-06-10", "due": "2026-06-15", "title": "Schedule team standup", "description": "Book a recurring 15-min daily standup.", "status":"Completed"},
        {"id": "T-004", "created": "2026-06-06", "due": "2026-06-10", "title": "Submit Meeting report", "description": "Submit meeting report to management.", "status":"Overdue"},
    ]


st.title("Lead Management System")

st.markdown('<hr style=height:1px;background:#d4d4d4; margin-bottom: 10px; margin-top: 0px;">', unsafe_allow_html=True)
st.markdown('<h2 style="margin-bottom: 10px;">Dashboard</h2>', unsafe_allow_html=True)

df = st.session_state.leads_df

total = len(df)
new = len(df[df["Status"] == "New"])
potent = len(df[df["Status"] == "Potential"])
non_pot = len(df[df["Status"] == "Non-Potential"])

col1, col2, col3, col4 = st.columns(4)
# with col1: st.metric(label="Total Leads", value=total)
# with col2: st.metric(label="New Leads", value=new)
# with col3: st.metric(label="Potential Leads", value=potent)
# with col4: st.metric(label="Non-Potential Leads", value=non_pot)
st.markdown(
    f"""
    <div style="
        display:grid;
        grid-template-columns: repeat(4, 1fr);
        gap:16px;
        margin-bottom:20px;
    ">
        {metric_card("Total Leads", total)}
        {metric_card("New Leads", new)}
        {metric_card("Potential Leads", potent)}
        {metric_card("Non-Potential Leads", non_pot)}
    </div>
    """,
    unsafe_allow_html=True,
)




# ── Filters ──
st.subheader("All Leads")
filter_col1, filter_col2, filter_col3 = st.columns(3)
with filter_col1:
    status_filter = st.multiselect(
        "Status Filter",
        options=["New", "In Progress", "Potential", "Non-Potential"],
    )
with filter_col2:
    rep_filter = st.multiselect(
        "Filter by rep",
        options=df["Assigned To"].unique(),
    )
with filter_col3:
    search_term = st.text_input("Search by Name or Company", value="", placeholder="Enter Name or Company here")

# Apply filters
if status_filter or rep_filter:
    filtered_df = df[
        (df["Status"].isin(status_filter) if status_filter else True) &
        (df["Assigned To"].isin(rep_filter) if rep_filter else True)
    ]
else:
    filtered_df = df.copy()

if search_term:
    mask = (
        filtered_df["Name"].str.contains(search_term, case=False, na=False) |
        filtered_df["Company"].str.contains(search_term, case=False, na=False)
    )
    filtered_df = filtered_df[mask]

st.caption(f"Showing {len(filtered_df)} of {len(df)} leads")

# ── Lead Cards ──
# CSS to make the invisible button overlay the HTML card
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
        border-color: #555;
        background-color: #f9f9f9;
        transform: translateY(-5px);
    }
</style>
""", unsafe_allow_html=True)

for idx, row in filtered_df.iterrows():
    lead = row

    # Status configuration: abbreviation + colors
    status_config = {
        "New":           {"abbr": "N",  "bg": "blue"},
        "In Progress":   {"abbr": "IP", "bg": "#FFC107"},
        "Potential":     {"abbr": "P",  "bg": "#4CAF50"},
        "Non-Potential": {"abbr": "NP", "bg": "Red"},
    }
    s = status_config.get(lead["Status"], {"abbr": "?", "bg": "#555"})

    # Render card matching wireframe
    st.markdown(
        f"""
        <div class="overlay-trigger" style="
            display: flex;
            border: 1px solid rgba(54,57,62,0.3);
            border-radius: 6px;
            margin-bottom: 12px;
            overflow: hidden;
            height: 75px;
            transition: transform 0.15 ease;
            background: white;
        ">
            <div style="flex:1; padding:12px 16px;">
                <div style="display:flex; align-items:baseline; gap:10px;">
                    <span style="color:#333; font-size:1.2rem; font-weight:600; line-height:1.2;">
                        {lead['Name']}
                    </span>
                    <span style="color:#666; font-size:0.85rem; font-weight:400; line-height:1.2;">
                        {lead['Company']}
                    </span>
                </div>
                <div style="margin-top:4px;">
                    <span style="color:#777; font-size:0.8rem; font-weight:400; line-height:1.2;">
                        Source: {lead['Source']} &nbsp;|&nbsp; Assigned To: {lead['Assigned To']}
                    </span>
                </div>
            </div>
            <div style="
                display:flex; align-items:center; justify-content:center;
                background:{s['bg']};
                min-width:64px; padding:0 14px;
            ">
                <span style="color: white; font-size:0.9rem; font-weight:600;">
                    {s['abbr']}
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Invisible Select button — opens the drawer dialog
    if st.button("Select", key=f"card_{lead['Lead ID']}", use_container_width=True):
        show_lead_panel(lead["Lead ID"], s['bg'])
