import streamlit as st
import asyncio
import time
from datetime import date, timedelta
from core.auth import require_login, logout
from components.report_engine import generate_chart_buffer, generate_docx_report
from core import api_client
from core.api_client import APIError
from core.state import state
from core.styles import inject_global_styles
from components.layout import render_sidebar

st.set_page_config(page_title="Reports", page_icon="", layout="wide")

inject_global_styles()


require_login()

TOKEN = state.token
USER = state.user or {}

# ── Sidebar ──
render_sidebar(key_suffix="report")

# ── Fetch leads for dropdown ──
try:
    leads = api_client.get_leads(TOKEN, limit=1000)
    lead_options = {l["id"]: f"{l['name']} — {l.get('profession') or 'N/A'}" for l in leads}
except APIError:
    leads = []
    lead_options = {}

# ── Page Header ──
st.markdown('<h1 style="display: inline; font-weight: 800;">Reports</h1><br>', unsafe_allow_html=True)

# ── Two main report tabs ──
tab1, tab2 = st.tabs(["Lead Journey Report", "Team Performance Digest"])

# ─────────────────────────────────────────────────────
# TAB 1: Lead Journey Report
# ─────────────────────────────────────────────────────
with tab1:
    st.subheader("Lead Journey Report")
    st.caption("AI-generated report analyzing a lead's complete journey through your pipeline.")

    if lead_options:
        selected_lead_id = st.selectbox(
            "Select Lead",
            options=list(lead_options.keys()),
            format_func=lambda x: lead_options.get(x, str(x)),
            key="journey_lead_select",
        )

        if st.button("Generate Report", key="gen_journey"):
            with st.spinner("Generating AI-powered lead journey report..."):
                try:
                    docx_bytes = api_client.download_lead_journey_report(TOKEN, selected_lead_id)
                    st.session_state["lead_journey_docx"] = docx_bytes
                    st.session_state["lead_journey_lead_name"] = lead_options[selected_lead_id]
                    st.success("Report generated successfully!")
                except APIError as e:
                    error_msg = str(e)
                    if "403" in error_msg:
                        st.error("You don't have access to generate reports for this lead.")
                    elif "404" in error_msg:
                        st.error("Lead not found.")
                    else:
                        st.error(f"Report generation failed: {e}")

        # Show download button if report was generated
        if "lead_journey_docx" in st.session_state:
            lead_name = st.session_state.get("lead_journey_lead_name", "lead")
            st.download_button(
                label="📄 Download Lead Journey Report (.docx)",
                data=st.session_state["lead_journey_docx"],
                file_name=f"lead_journey_{lead_name.split(' — ')[0].replace(' ', '_').lower()}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="dl_journey",
            )
    else:
        st.warning("No leads found. Create some leads first.")

# ─────────────────────────────────────────────────────
# TAB 2: Team Performance Digest
# ─────────────────────────────────────────────────────
with tab2:
    st.subheader("Team Performance Digest")
    st.caption("AI-generated team performance analysis. Admin/Manager only.")

    if USER.get("role") in ("admin", "manager"):
        if st.button("Generate Performance Report", key="gen_perf"):
            with st.spinner("Compiling team metrics and generating AI analysis..."):
                try:
                    docx_bytes = api_client.download_team_performance_report(TOKEN)
                    st.session_state["team_perf_docx"] = docx_bytes
                    st.success("Team performance report generated successfully!")
                except APIError as e:
                    st.error(f"Report generation failed: {e}")

        if "team_perf_docx" in st.session_state:
            st.download_button(
                label="📄 Download Team Performance Report (.docx)",
                data=st.session_state["team_perf_docx"],
                file_name="team_performance_digest.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="dl_perf",
            )
    else:
        st.warning("Team performance reports are only available to Admins and Managers.")
