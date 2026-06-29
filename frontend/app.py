import streamlit as st
from datetime import datetime, date
from components.auth_guard import require_login
import api_client

st.set_page_config(
    page_title="Lead Management System",
    page_icon="",
    layout="wide"
)

# ── Auth gate ──
require_login()

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

TOKEN = st.session_state.token
USER = st.session_state.user


# ── Helper functions ──
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

STATUS_DISPLAY = {
    "new": "New",
    "in_progress": "In Progress",
    "potential": "Potential",
    "non_potential": "Non-Potential",
    "converted_to_investor": "Converted",
}

STATUS_OPTIONS_API = ["new", "in_progress", "potential", "non_potential", "converted_to_investor"]
STATUS_OPTIONS_DISPLAY = [STATUS_DISPLAY[s] for s in STATUS_OPTIONS_API]


# ── Lead Detail Drawer ──
@st.dialog(" ", width="medium")
def show_lead_panel(lead_id, status_color):
    try:
        lead = api_client.get_lead(TOKEN, lead_id)
    except Exception as e:
        st.error(f"Failed to load lead: {e}")
        return

    display_status = STATUS_DISPLAY.get(lead["status"], lead["status"])

    st.markdown(f"""<h1 style="display: inline; font-weight: 800;">{lead["name"]}</h1>&nbsp;&nbsp;<h4 style="display: inline; font-weight: 400;">{lead.get("profession") or ""}</h4>""", unsafe_allow_html=True)
    st.markdown("---")

    # Details section
    st.markdown('<h2>Details</h2>', unsafe_allow_html=True)
    source_col, assignedTo_col = st.columns(2)
    with source_col: st.markdown(f"**Source:** {lead.get('source_name') or 'N/A'}")
    with assignedTo_col: st.markdown(f"**Assigned To:** {lead.get('assigned_rep_name') or 'N/A'}")

    email_col, phone_col = st.columns(2)
    with email_col: st.markdown(f"**Email:** {lead.get('email') or 'N/A'}")
    with phone_col: st.markdown(f"**Phone No:** {lead.get('phone_number') or 'N/A'}")

    lastContact_col, status_col = st.columns(2)
    with lastContact_col: st.markdown(f"**Last Contact:** {lead.get('last_contact') or 'N/A'}")
    with status_col: st.markdown(f"**Status:** {status_span(display_status, status_color)}", unsafe_allow_html=True)

    if lead.get("address"):
        st.markdown(f"**Address:** {lead['address']}")

    st.markdown("---")

    # Update Lead section
    st.markdown('<h2>Update Lead</h2>', unsafe_allow_html=True)

    current_idx = STATUS_OPTIONS_API.index(lead["status"]) if lead["status"] in STATUS_OPTIONS_API else 0

    status_col_u, date_col = st.columns(2)
    with status_col_u:
        new_status_display = st.selectbox(
            "Change Status",
            options=STATUS_OPTIONS_DISPLAY,
            index=current_idx,
        )
    with date_col:
        try:
            current_date = datetime.strptime(lead["last_contact"], "%Y-%m-%d").date() if lead.get("last_contact") else datetime.now().date()
        except:
            current_date = datetime.now().date()
        new_last_contact = st.date_input("Last Contact", value=current_date)

    if st.button("Update Lead Details", use_container_width=True, type="primary"):
        new_status_api = STATUS_OPTIONS_API[STATUS_OPTIONS_DISPLAY.index(new_status_display)]
        update_data = {}
        if new_status_api != lead["status"]:
            update_data["status"] = new_status_api
        if new_last_contact.isoformat() != (lead.get("last_contact") or ""):
            update_data["last_contact"] = new_last_contact.isoformat()

        if update_data:
            try:
                api_client.update_lead(TOKEN, lead_id, update_data)
                st.toast("Lead updated successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Update failed: {e}")
        else:
            st.toast("No changes to save.")

    st.markdown("---")

    # Interaction History
    st.markdown("<h2>Interaction History</h2>", unsafe_allow_html=True)
    with st.form(key=f"note_form_{lead_id}", clear_on_submit=True):
        notes = st.text_area("Add a new note", height=100, placeholder="Enter call notes here...")
        submitted = st.form_submit_button("Add Note", use_container_width=True)
        if submitted and notes.strip():
            try:
                api_client.add_timeline_note(TOKEN, lead_id, "note", {"note": notes.strip()})
                st.rerun()
            except Exception as e:
                st.error(f"Failed to add note: {e}")

    # Show timeline
    st.markdown("<br>", unsafe_allow_html=True)
    try:
        timeline = api_client.get_timeline(TOKEN, lead_id)
        if timeline:
            for entry in timeline:
                ts = entry["created_at"][:16].replace("T", " ")
                event_type = entry["event_type"]
                meta = entry.get("event_metadata", {})
                user_name = entry.get("user_name", "")

                if event_type == "status_change":
                    old = STATUS_DISPLAY.get(meta.get("old_status", ""), meta.get("old_status", ""))
                    new = STATUS_DISPLAY.get(meta.get("new_status", ""), meta.get("new_status", ""))
                    note_text = meta.get("note", "")
                    st.markdown(f"**{ts}** — `{old} → {new}`\n\n_{note_text}_" if note_text else f"**{ts}** — `{old} → {new}`")
                elif event_type == "note":
                    st.markdown(f"**{ts}** — _{meta.get('note', '')}_")
                elif event_type == "lead_created":
                    st.markdown(f"**{ts}** — Lead created from {meta.get('source', 'unknown source')}")
                elif event_type == "appointment_booked":
                    st.markdown(f"**{ts}** — Appointment: {meta.get('title', '')}")
                else:
                    st.markdown(f"**{ts}** — {event_type}")
                st.markdown("---")
        else:
            st.caption("No timeline entries yet.")
    except Exception as e:
        st.error(f"Failed to load timeline: {e}")


# ── Fetch data from API ──
try:
    leads = api_client.get_leads(TOKEN)
except Exception as e:
    st.error(f"Failed to load leads: {e}")
    leads = []

# ── Sidebar: User info + Logout ──
with st.sidebar:
    st.markdown(f"**{USER.get('name', '')}**")
    st.caption(f"{USER.get('role', '').replace('_', ' ').title()} — {USER.get('email', '')}")
    if st.button("Logout", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# ── Page Header ──
st.title("Lead Management System")
st.markdown('<hr style=height:1px;background:#d4d4d4; margin-bottom: 10px; margin-top: 0px;">', unsafe_allow_html=True)
st.markdown('<h2 style="margin-bottom: 10px;">Dashboard</h2>', unsafe_allow_html=True)

# ── Metrics ──
total = len(leads)
new = len([l for l in leads if l["status"] == "new"])
potent = len([l for l in leads if l["status"] == "potential"])
non_pot = len([l for l in leads if l["status"] == "non_potential"])
converted = len([l for l in leads if l["status"] == "converted_to_investor"])

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
        {metric_card("Converted", converted)}
    </div>
    """,
    unsafe_allow_html=True,
)


# ── Filters ──
st.subheader("All Leads")

# Get unique assigned reps and sources from the leads data
rep_names = sorted(set(l.get("assigned_rep_name", "") for l in leads if l.get("assigned_rep_name")))
source_names = sorted(set(l.get("source_name", "") for l in leads if l.get("source_name")))

filter_col1, filter_col2, filter_col3 = st.columns(3)
with filter_col1:
    status_filter = st.multiselect(
        "Status Filter",
        options=list(STATUS_DISPLAY.values()),
    )
with filter_col2:
    rep_filter = st.multiselect(
        "Filter by rep",
        options=rep_names,
    )
with filter_col3:
    search_term = st.text_input("Search by Name", value="", placeholder="Enter Name here")

# Apply client-side filters
filtered_leads = leads
if status_filter:
    api_statuses = [k for k, v in STATUS_DISPLAY.items() if v in status_filter]
    filtered_leads = [l for l in filtered_leads if l["status"] in api_statuses]
if rep_filter:
    filtered_leads = [l for l in filtered_leads if l.get("assigned_rep_name") in rep_filter]
if search_term:
    term = search_term.lower()
    filtered_leads = [l for l in filtered_leads if term in l["name"].lower() or term in (l.get("profession") or "").lower()]

st.caption(f"Showing {len(filtered_leads)} of {len(leads)} leads")


# ── Lead Cards ──
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
        border-color: #555;
        background-color: #f9f9f9;
        transform: translateY(-5px);
    }
</style>
""", unsafe_allow_html=True)

status_config = {
    "new":           {"abbr": "N",  "bg": "blue"},
    "in_progress":   {"abbr": "IP", "bg": "#FFC107"},
    "potential":     {"abbr": "P",  "bg": "#4CAF50"},
    "non_potential": {"abbr": "NP", "bg": "Red"},
    "converted_to_investor": {"abbr": "C", "bg": "#2196F3"},
}

for lead in filtered_leads:
    s = status_config.get(lead["status"], {"abbr": "?", "bg": "#555"})
    display_status = STATUS_DISPLAY.get(lead["status"], lead["status"])

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
                        {lead['name']}
                    </span>
                    <span style="color:#666; font-size:0.85rem; font-weight:400; line-height:1.2;">
                        {lead.get('profession') or ''}
                    </span>
                </div>
                <div style="margin-top:4px;">
                    <span style="color:#777; font-size:0.8rem; font-weight:400; line-height:1.2;">
                        Source: {lead.get('source_name') or 'N/A'} &nbsp;|&nbsp; Assigned To: {lead.get('assigned_rep_name') or 'N/A'}
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
    if st.button("Select", key=f"card_{lead['id']}", use_container_width=True):
        show_lead_panel(lead["id"], s['bg'])
