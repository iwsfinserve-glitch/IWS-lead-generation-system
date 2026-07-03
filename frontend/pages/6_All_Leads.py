import streamlit as st
from datetime import datetime
from core.auth import require_login, logout
from core import api_client
from core.state import state
from core.api_client import APIError
from core.styles import inject_global_styles
from components.layout import render_sidebar, render_pagination
from components.modals import (
    show_lead_panel, STATUS_DISPLAY, STATUS_CONFIG, ACTIVE_STATUSES,
    STATUS_OPTIONS_API, STATUS_OPTIONS_DISPLAY,
)
from components.cards import render_lead_cards

st.set_page_config(
    page_title="All Leads Directory",
    page_icon="",
    layout="wide"
)

inject_global_styles(drawer=True, overlay_cards=True)


# ── Constants ───────────────────────────────────────────────────────
PAGE_SIZE = 15





# ═════════════════════════════════════════════════════════════════════
# PAGE ENTRY POINT
# ═════════════════════════════════════════════════════════════════════
require_login()

TOKEN = state.token
USER = state.user or {}

# ── Sidebar: User info + Logout ──
render_sidebar(key_suffix="allleads")

# ── Init pagination state ──
if "active_page" not in st.session_state:
    st.session_state.active_page = 1
if "converted_page" not in st.session_state:
    st.session_state.converted_page = 1

# ── Page Header ──
st.title("All Leads Directory")
st.markdown('<hr style="height:1px;background:#d4d4d4; margin-bottom: 10px; margin-top: 0px;">', unsafe_allow_html=True)

# ── Fetch all leads ──
try:
    all_leads = api_client.get_leads(TOKEN, limit=1000)
except APIError as e:
    st.error(f"Failed to load leads: {e}")
    st.stop()

# ── Split into active vs converted ──
active_leads = [l for l in all_leads if l["status"] in ACTIVE_STATUSES]
converted_leads = [l for l in all_leads if l["status"] == "converted_to_investor"]

# ── Global Filters ──
rep_names = sorted(set(l.get("assigned_rep_name", "") for l in all_leads if l.get("assigned_rep_name")))

filter_col1, filter_col2, filter_col3 = st.columns(3)
with filter_col1:
    status_filter = st.multiselect(
        "Status Filter",
        options=["New", "In Progress", "Potential", "Non-Potential"],
        key="allleads_status_filter",
    )
with filter_col2:
    rep_filter = st.multiselect(
        "Filter by Rep",
        options=rep_names,
        key="allleads_rep_filter",
    )
with filter_col3:
    search_term = st.text_input(
        "Search by Name or Profession",
        value="",
        placeholder="Enter Name or Profession here",
        key="allleads_search",
    )


def apply_filters(leads_list, apply_status_filter=True):
    """Apply the global filters to a list of leads."""
    filtered = leads_list

    # Status filter only applies to the Active tab
    if apply_status_filter and status_filter:
        api_statuses = [k for k, v in STATUS_DISPLAY.items() if v in status_filter]
        filtered = [l for l in filtered if l["status"] in api_statuses]

    if rep_filter:
        filtered = [l for l in filtered if l.get("assigned_rep_name") in rep_filter]

    if search_term:
        term = search_term.lower()
        filtered = [
            l for l in filtered
            if term in l["name"].lower() or term in (l.get("profession") or "").lower()
        ]

    return filtered


# ── Tabs ────────────────────────────────────────────────────────────
tab_active, tab_converted = st.tabs([
    f"Active ({len(active_leads)})",
    f"Converted ({len(converted_leads)})",
])

with tab_active:
    filtered_active = apply_filters(active_leads, apply_status_filter=True)

    # Paginate
    skip = (st.session_state.active_page - 1) * PAGE_SIZE
    page_leads = filtered_active[skip : skip + PAGE_SIZE]

    st.caption(f"Showing {len(page_leads)} of {len(filtered_active)} active leads")

    if page_leads:
        render_lead_cards(page_leads, key_prefix="active_card", on_click=show_lead_panel)
        render_pagination(len(filtered_active), "active_page", page_size=PAGE_SIZE)
    else:
        st.info("No active leads match the current filters.")

with tab_converted:
    # Status filter doesn't apply here — converted tab has only one status
    filtered_converted = apply_filters(converted_leads, apply_status_filter=False)

    skip = (st.session_state.converted_page - 1) * PAGE_SIZE
    page_leads = filtered_converted[skip : skip + PAGE_SIZE]

    st.caption(f"Showing {len(page_leads)} of {len(filtered_converted)} converted leads")

    if page_leads:
        render_lead_cards(page_leads, key_prefix="converted_card", on_click=show_lead_panel)
        render_pagination(len(filtered_converted), "converted_page", page_size=PAGE_SIZE)
    else:
        st.info("No converted leads match the current filters.")
