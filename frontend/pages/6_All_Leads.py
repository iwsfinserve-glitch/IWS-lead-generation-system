import html
import streamlit as st
import time
from datetime import datetime
from core.auth import require_login, logout
from core import api_client
from core.state import state
from core.api_client import APIError, APIConflictError
from core.styles import inject_global_styles
from components.layout import render_sidebar, render_pagination, render_divider
from components.modals import (
    STATUS_DISPLAY, STATUS_CONFIG, ACTIVE_STATUSES,
    STATUS_OPTIONS_API, STATUS_OPTIONS_DISPLAY, create_lead_dialog,
)
from components.cards import render_lead_cards, render_request_cards

st.set_page_config(
    page_title="All Leads Directory",
    page_icon="",
    layout="wide"
)

inject_global_styles(overlay_cards=True)


def navigate_to_lead(lead_id: int, status_color: str = "") -> None:
    """Navigate to the dedicated Lead Details page."""
    st.session_state.selected_lead_id = lead_id
    st.session_state.lead_details_origin = "pages/6_All_Leads.py"
    st.switch_page("pages/7_Lead_Details.py")


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

# ── Silent background data refresh (30-second polling, no page reload) ──
if "allleads_last_refresh" not in st.session_state:
    st.session_state.allleads_last_refresh = time.time()

if time.time() - st.session_state.allleads_last_refresh > 30:
    api_client.get_leads.clear()
    st.session_state.allleads_last_refresh = time.time()

# ── Init pagination state ──
if "active_page" not in st.session_state:
    st.session_state.active_page = 1
if "unassigned_page" not in st.session_state:
    st.session_state.unassigned_page = 1
if "converted_page" not in st.session_state:
    st.session_state.converted_page = 1
if "ei_page" not in st.session_state:
    st.session_state.ei_page = 1
if "sorted_all_page" not in st.session_state:
    st.session_state.sorted_all_page = 1

# ── Page Header ──
st.title("All Leads Directory")
render_divider()

if st.button("Create New Lead", type="primary", key="allleads_create_btn"):
    create_lead_dialog()

# ── Global Filters & Data Fetching ──
try:
    sales_reps = api_client.get_sales_reps(TOKEN)
    rep_map = {r["name"]: r["id"] for r in sales_reps}
    rep_names = sorted(list(rep_map.keys()))
except Exception:
    rep_names = []
    rep_map = {}

filter_col1, filter_col2, filter_col3 = st.columns(3)
with filter_col1:
    status_filter = st.multiselect(
        "Status Filter",
        options=["Unassigned", "In Progress", "Potential", "Non-Potential"],
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

# Optimized server-side filters passing
status_val = None
if status_filter and len(status_filter) == 1:
    # Map display names to API status codes
    status_display_map = {
        "Unassigned": "unassigned",
        "In Progress": "in_progress",
        "Potential": "potential",
        "Non-Potential": "non_potential",
    }
    status_val = status_display_map.get(status_filter[0])

rep_id_val = None
if rep_filter and len(rep_filter) == 1:
    rep_id_val = rep_map.get(rep_filter[0])

search_val = search_term.strip() if search_term.strip() else None

# Fetch leads with database-side filters
try:
    all_leads = api_client.get_leads(
        TOKEN,
        status=status_val,
        assigned_rep_id=rep_id_val,
        search=search_val,
        limit=1000
    )
except APIError as e:
    st.error(f"Failed to load leads: {e}")
    st.stop()

# ── Fetch server-side summary counts (efficient, no full data transfer) ──
try:
    summary_counts = api_client.get_leads_summary(TOKEN)
except Exception:
    summary_counts = None

# ── Split into sections ──
unassigned_leads = [l for l in all_leads if l.get("assigned_rep_id") is None and l.get("status") not in {"converted_to_investor", "existing_investor"}]
active_leads = [l for l in all_leads if l.get("assigned_rep_id") is not None and l.get("status") not in {"converted_to_investor", "existing_investor"}]
converted_leads = [l for l in all_leads if l.get("status") == "converted_to_investor"]
existing_investors = [l for l in all_leads if l.get("status") == "existing_investor"]

user_role = USER.get("role", "sales_rep")
is_manager = user_role in ("manager", "admin")
is_sales_rep = user_role == "sales_rep"


def apply_filters(leads_list, apply_status_filter=True):
    """Apply the global filters to a list of leads (fallback for multi-selects)."""
    filtered = leads_list

    if apply_status_filter and status_filter and len(status_filter) > 1:
        api_statuses = [k for k, v in STATUS_DISPLAY.items() if v in status_filter]
        filtered = [l for l in filtered if l["status"] in api_statuses]

    if rep_filter and len(rep_filter) > 1:
        filtered = [l for l in filtered if l.get("assigned_rep_name") in rep_filter]

    if search_term and not search_val:
        term = search_term.lower()
        filtered = [
            l for l in filtered
            if term in l["name"].lower() or term in (l.get("profession") or "").lower()
        ]

    return filtered


def render_claim_button(lead: dict, key_prefix: str = "claim") -> None:
    """Render a Claim Lead button for unassigned leads (sales reps and managers)."""
    lead_id = lead["id"]
    btn_key = f"{key_prefix}_{lead_id}"
    if st.button("Claim Lead", key=btn_key, type="primary"):
        try:
            api_client.claim_lead(TOKEN, lead_id)
            st.toast("Lead claimed successfully. You are now assigned to this lead.")
            st.rerun()
        except APIConflictError as e:
            st.warning(str(e))
            api_client.get_leads.clear()
            st.rerun()
        except APIError as e:
            st.error(f"Failed to claim lead: {e}")


# ── Fetch pending transfer requests for managers/admins ──
transfer_requests = []
if is_manager:
    try:
        transfer_requests = api_client.get_lead_transfer_requests(TOKEN, status="pending")
    except APIError:
        transfer_requests = []

# ── Tabs ────────────────────────────────────────────────────────────
# Use server-side summary counts for tab labels when available (faster, accurate)
_sc = summary_counts or {}
_total = _sc.get("total", len(all_leads))
_unassigned_count = _sc.get("unassigned", len(unassigned_leads))
_active_count = _sc.get("in_progress", 0) + _sc.get("potential", 0) + _sc.get("non_potential", 0) if summary_counts else len(active_leads)
_converted_count = _sc.get("converted_to_investor", len(converted_leads))
_ei_count = _sc.get("existing_investor", len(existing_investors))

if is_manager:
    tab_sorted, tab_unassigned, tab_active, tab_converted, tab_ei, tab_transfers = st.tabs([
        f"All Leads ({_total})",
        f"Unassigned ({_unassigned_count})",
        f"Active ({_active_count})",
        f"Converted ({_converted_count})",
        f"Existing Investors ({_ei_count})",
        f"Transfer Requests ({len(transfer_requests)})",
    ])
else:
    tab_sorted, tab_unassigned, tab_active, tab_converted, tab_ei = st.tabs([
        f"All Leads ({_total})",
        f"Unassigned ({_unassigned_count})",
        f"Active ({_active_count})",
        f"Converted ({_converted_count})",
        f"Existing Investors ({_ei_count})",
    ])

# ── All (Sorted) Tab ────────────────────────────────────────────────
with tab_sorted: 
    filtered_sorted = apply_filters(all_leads, apply_status_filter=True)

    priority_map = {"high": 0, "medium": 1, "low": 2}
    sorted_leads = sorted(
        filtered_sorted,
        key=lambda l: (
            0 if l.get("assigned_rep_id") is None else 1,
            priority_map.get((l.get("source_priority") or "medium").lower(), 1),
            (l.get("name") or "").lower()
        )
    )

    skip = (st.session_state.sorted_all_page - 1) * PAGE_SIZE
    page_leads = sorted_leads[skip: skip + PAGE_SIZE]

    st.caption(f"Showing {len(page_leads)} of {len(sorted_leads)} leads (sorted by priority)")

    if page_leads:
        for lead in page_leads:
            if lead.get("assigned_rep_id") is None:
                col_lead, col_btn = st.columns([5, 1])
                with col_lead:
                    render_lead_cards([lead], key_prefix=f"sort_card_{lead['id']}", on_click=navigate_to_lead)
                with col_btn:
                    st.write("")  # vertical spacer
                    render_claim_button(lead, key_prefix="sort_claim")
            else:
                render_lead_cards([lead], key_prefix=f"sort_card_{lead['id']}", on_click=navigate_to_lead)
        render_pagination(len(sorted_leads), "sorted_all_page", page_size=PAGE_SIZE)
    else:
        st.info("No leads match the current filters.")

# ── Unassigned Tab ──────────────────────────────────────────────────
with tab_unassigned:
    filtered_unassigned = unassigned_leads

    if search_val:
        term = search_val.lower()
        filtered_unassigned = [
            l for l in filtered_unassigned
            if term in l["name"].lower() or term in (l.get("profession") or "").lower()
        ]

    skip = (st.session_state.unassigned_page - 1) * PAGE_SIZE
    page_leads = filtered_unassigned[skip: skip + PAGE_SIZE]

    st.caption(f"Showing {len(page_leads)} of {len(filtered_unassigned)} unassigned leads")

    if page_leads:
        for lead in page_leads:
            col_lead, col_btn = st.columns([5, 1])
            with col_lead:
                render_lead_cards([lead], key_prefix=f"ua_card_{lead['id']}", on_click=navigate_to_lead)
            with col_btn:
                st.write("")  # vertical spacer
                render_claim_button(lead, key_prefix="ua_claim")
        render_pagination(len(filtered_unassigned), "unassigned_page", page_size=PAGE_SIZE)
    else:
        st.info("No unassigned leads at this time.")

# ── Active Tab ──────────────────────────────────────────────────────
with tab_active:
    filtered_active = apply_filters(active_leads, apply_status_filter=True)

    skip = (st.session_state.active_page - 1) * PAGE_SIZE
    page_leads = filtered_active[skip: skip + PAGE_SIZE]

    st.caption(f"Showing {len(page_leads)} of {len(filtered_active)} active leads")

    if page_leads:
        render_lead_cards(page_leads, key_prefix="active_card", on_click=navigate_to_lead)
        render_pagination(len(filtered_active), "active_page", page_size=PAGE_SIZE)
    else:
        st.info("No active leads match the current filters.")

with tab_converted:
    filtered_converted = apply_filters(converted_leads, apply_status_filter=False)

    skip = (st.session_state.converted_page - 1) * PAGE_SIZE
    page_leads = filtered_converted[skip: skip + PAGE_SIZE]

    st.caption(f"Showing {len(page_leads)} of {len(filtered_converted)} converted leads")

    if page_leads:
        render_lead_cards(page_leads, key_prefix="converted_card", on_click=navigate_to_lead)
        render_pagination(len(filtered_converted), "converted_page", page_size=PAGE_SIZE)
    else:
        st.info("No converted leads match the current filters.")

with tab_ei:
    filtered_ei = apply_filters(existing_investors, apply_status_filter=False)

    skip = (st.session_state.ei_page - 1) * PAGE_SIZE
    page_leads = filtered_ei[skip: skip + PAGE_SIZE]

    st.caption(f"Showing {len(page_leads)} of {len(filtered_ei)} existing investors")

    if page_leads:
        render_lead_cards(page_leads, key_prefix="ei_card", on_click=navigate_to_lead)
        render_pagination(len(filtered_ei), "ei_page", page_size=PAGE_SIZE)
    else:
        st.info("No existing investors match the current filters.")

# ── Transfer Requests Tab (manager/admin only) ──────────────────────
if is_manager:
    with tab_transfers:
        if not transfer_requests:
            st.info("No pending transfer requests.")
        else:
            st.caption(f"{len(transfer_requests)} pending transfer request(s)")

            def _approve_transfer(req_id):
                try:
                    api_client.update_lead_transfer_request(TOKEN, req_id, {"status": "approved"})
                    st.toast("Transfer approved!")
                    st.rerun()
                except APIError as e:
                    st.error(f"Failed: {e}")

            def _reject_transfer(req_id):
                try:
                    api_client.update_lead_transfer_request(TOKEN, req_id, {"status": "rejected"})
                    st.toast("Transfer rejected.")
                    st.rerun()
                except APIError as e:
                    st.error(f"Failed: {e}")

            render_request_cards(
                transfer_requests,
                key_prefix="tr",
                title_field="lead_name",
                subtitle_fn=lambda r: f"<b>{html.escape(str(r.get('from_user_name', 'Unknown')))}</b> to <b>{html.escape(str(r.get('to_user_name', 'Unknown')))}</b>",
                detail_fn=lambda r: html.escape(str(r.get("reason") or "-")),
                on_approve=_approve_transfer,
                on_reject=_reject_transfer,
            )
