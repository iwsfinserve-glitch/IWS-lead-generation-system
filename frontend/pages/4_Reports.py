import streamlit as st
import pandas as pd
import base64
import html
import io
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta
from core.auth import require_login
from core import api_client
from core.api_client import APIError
from core.state import state
from core.styles import inject_global_styles
from components.layout import render_sidebar

st.set_page_config(page_title="Reports | IWS Finserve", page_icon="📊", layout="wide")
inject_global_styles()
require_login()

TOKEN = state.token
USER = state.user or {}
ROLE = USER.get("role", "sales_rep")

render_sidebar(key_suffix="reports")


st.markdown("""
<div class="report-header">
  <h1>Reports</h1>
</div>
""", unsafe_allow_html=True)


# ── Date range selector ───────────────────────────────────────────────────────
def date_range_selector(key_prefix: str):
    preset = st.selectbox(
        "Time Period",
        ["Last 30 Days", "Last Month", "Last Quarter", "Last Year", "All Time", "Custom Range"],
        key=f"{key_prefix}_period",
    )
    today = date.today()
    if preset == "Last 30 Days":
        sd, ed = today - timedelta(days=30), today
    elif preset == "Last Month":
        first = today.replace(day=1)
        sd = (first - timedelta(days=1)).replace(day=1)
        ed = first - timedelta(days=1)
    elif preset == "Last Quarter":
        sd, ed = today - timedelta(days=90), today
    elif preset == "Last Year":
        sd, ed = today - timedelta(days=365), today
    elif preset == "All Time":
        sd, ed = None, None
    else:
        c1, c2 = st.columns(2)
        sd = c1.date_input("Start Date", value=today - timedelta(days=30), key=f"{key_prefix}_sd")
        ed = c2.date_input("End Date", value=today, key=f"{key_prefix}_ed")
    period_label = preset if preset != "Custom Range" else f"{sd} to {ed}"
    sd_str = sd.isoformat() if sd else None
    ed_str = ed.isoformat() if ed else None
    return sd_str, ed_str, period_label


# ── Chart helpers ─────────────────────────────────────────────────────────────
STATUS_COLORS = {
    "new": "#3b82f6", "in_progress": "#f59e0b", "potential": "#8b5cf6",
    "converted_to_investor": "#10b981", "existing_investor": "#059669",
    "non_potential": "#ef4444",
}
STATUS_LABELS = {
    "new": "New", "in_progress": "In Progress", "potential": "Potential",
    "converted_to_investor": "Converted", "existing_investor": "Existing Investor",
    "non_potential": "Non-Potential",
}


def render_leads_metrics(metrics: dict):
    by_status = metrics.get("by_status", {})
    by_source = metrics.get("by_source", {})
    total = metrics.get("total_leads", 0)
    converted = metrics.get("converted_leads", 0)
    conv_rate = metrics.get("conversion_rate", 0)

    cols = st.columns(4)
    cards = [
        ("Total Leads", total),
        ("Converted", converted),
        ("Conversion Rate", f"{conv_rate}%"),
        ("Pipeline Stages", len(by_status)),
    ]
    for col, (lbl, val) in zip(cols, cards):
        col.markdown(f"""
        <div class="metric-card">
          <div class="val">{val}</div>
          <div class="lbl">{lbl}</div>
        </div>""", unsafe_allow_html=True)

    if by_status:
        c1, c2 = st.columns(2)
        with c1:
            labels = [STATUS_LABELS.get(k, k) for k in by_status]
            colors = [STATUS_COLORS.get(k, "#94a3b8") for k in by_status]
            fig = go.Figure(go.Pie(
                labels=labels, values=list(by_status.values()),
                marker=dict(colors=colors), hole=0.45,
                textinfo="percent+label",
            ))
            fig.update_layout(title="Pipeline Distribution", height=320,
                              margin=dict(t=40, b=0, l=0, r=0),
                              showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            if by_source:
                df_src = pd.DataFrame({"Source": list(by_source.keys()), "Leads": list(by_source.values())})
                fig2 = px.bar(df_src, x="Leads", y="Source", orientation="h",
                              color="Leads", color_continuous_scale="Blues",
                              title="Leads by Acquisition Channel")
                fig2.update_layout(height=320, margin=dict(t=40, b=0, l=0, r=0),
                                   coloraxis_showscale=False)
                st.plotly_chart(fig2, use_container_width=True)

    leads_list = metrics.get("leads", [])
    if leads_list:
        st.markdown('<div class="section-title">Lead Details</div>', unsafe_allow_html=True)
        df = pd.DataFrame(leads_list)[["name", "profession", "status", "source", "ai_score", "ai_score_label", "created_at"]]
        df.columns = ["Name", "Profession", "Status", "Source", "AI Score", "Label", "Created"]
        df["Status"] = df["Status"].map(STATUS_LABELS).fillna(df["Status"])
        st.dataframe(df, use_container_width=True, hide_index=True)


def render_performance_metrics(metrics: dict):
    cols = st.columns(4)
    cards = [
        ("Leads Assigned", metrics.get("total_leads_assigned", 0)),
        ("Converted", metrics.get("converted_leads", 0)),
        ("Conversion Rate", f"{metrics.get('conversion_rate', 0)}%"),
        ("Appointments", metrics.get("total_appointments", 0)),
    ]
    for col, (lbl, val) in zip(cols, cards):
        col.markdown(f'<div class="metric-card"><div class="val">{val}</div><div class="lbl">{lbl}</div></div>',
                     unsafe_allow_html=True)

    st.markdown("")
    cols2 = st.columns(3)
    cards2 = [
        ("Total Tasks", metrics.get("total_tasks", 0)),
        ("Tasks Completed", metrics.get("tasks_completed", 0)),
        ("Completion Rate", f"{metrics.get('task_completion_rate', 0)}%"),
    ]
    for col, (lbl, val) in zip(cols2, cards2):
        col.markdown(f'<div class="metric-card"><div class="val">{val}</div><div class="lbl">{lbl}</div></div>',
                     unsafe_allow_html=True)

    by_status = metrics.get("by_status", {})
    if by_status:
        labels = [STATUS_LABELS.get(k, k) for k in by_status]
        colors = [STATUS_COLORS.get(k, "#94a3b8") for k in by_status]
        fig = go.Figure(go.Bar(
            x=labels, y=list(by_status.values()),
            marker_color=colors,
        ))
        fig.update_layout(title="Lead Pipeline Breakdown", height=280,
                          margin=dict(t=40, b=0, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)


def render_team_metrics(data: dict):
    totals = data.get("totals", {})
    cols = st.columns(4)
    cards = [
        ("Team Members", data.get("member_count", 0)),
        ("Total Leads", totals.get("total_leads", 0)),
        ("Converted", totals.get("converted_leads", 0)),
        ("Avg Conversion", f"{totals.get('avg_conversion_rate', 0)}%"),
    ]
    for col, (lbl, val) in zip(cols, cards):
        col.markdown(f'<div class="metric-card"><div class="val">{val}</div><div class="lbl">{lbl}</div></div>',
                     unsafe_allow_html=True)

    members = data.get("members", [])
    if members:
        df = pd.DataFrame(members)
        c1, c2 = st.columns(2)
        with c1:
            fig = px.bar(df, x="user_name", y="total_leads_assigned",
                         color="conversion_rate", color_continuous_scale="Blues",
                         title="Leads per Team Member")
            fig.update_layout(height=300, margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig2 = px.bar(df, x="user_name", y=["tasks_completed", "total_appointments"],
                          barmode="group", title="Tasks Completed & Appointments")
            fig2.update_layout(height=300, margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown('<div class="section-title">Team Member Summary</div>', unsafe_allow_html=True)
        display_cols = ["user_name", "user_role", "total_leads_assigned", "converted_leads",
                        "conversion_rate", "total_appointments", "tasks_completed"]
        disp_df = df[[c for c in display_cols if c in df.columns]].copy()
        disp_df.columns = ["Name", "Role", "Leads", "Converted", "Conv%", "Appts", "Tasks Done"][:len(disp_df.columns)]
        st.dataframe(disp_df, use_container_width=True, hide_index=True)


def show_narrative(narrative: str):
    st.markdown('<div class="section-title">AI Analysis Narrative</div>', unsafe_allow_html=True)
    safe_narrative = html.escape(str(narrative or "")).replace("\n", "<br>")
    st.markdown(f'<div class="narrative-box">{safe_narrative}</div>', unsafe_allow_html=True)


# ── Fetch common data ─────────────────────────────────────────────────────────
try:
    leads = api_client.get_leads(TOKEN, limit=1000)
    lead_options = {l["id"]: f"{l['name']} ({l.get('profession') or 'N/A'})" for l in leads}
except APIError:
    leads, lead_options = [], {}

all_users = []
if ROLE in ("admin", "manager"):
    try:
        all_users = api_client.get_users(TOKEN)
    except APIError:
        all_users = []

sales_reps = [u for u in all_users if u["role"] == "sales_rep"]
managers = [u for u in all_users if u["role"] == "manager"]

if ROLE == "manager":
    user_id = USER.get("id")
    sales_reps = [u for u in sales_reps if u.get("manager_id") == user_id]


# ── Build tabs based on role ──────────────────────────────────────────────────
if ROLE == "sales_rep":
    tab_names = ["Lead Journey", "Periodic Leads Report"]
    tabs = st.tabs(tab_names)
    t_journey, t_periodic = tabs[0], tabs[1]
    t_perf, t_team = None, None
elif ROLE == "manager":
    tab_names = ["Lead Journey", "Periodic Leads Report", "Rep Performance", "Team Digest"]
    tabs = st.tabs(tab_names)
    t_journey, t_periodic, t_perf, t_team = tabs
else:  # admin
    tab_names = ["Lead Journey", "Periodic Leads Report", "Individual Performance", "Team Digest"]
    tabs = st.tabs(tab_names)
    t_journey, t_periodic, t_perf, t_team = tabs


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1: Lead Journey Report
# ─────────────────────────────────────────────────────────────────────────────
with t_journey:
    st.markdown("#### Lead Journey Report")
    st.caption("AI-generated narrative of a lead's full engagement history — status changes, interactions, notes, and advisor next steps.")

    if not lead_options:
        st.warning("No leads found.")
    else:
        sel_id = st.selectbox("Select Lead", list(lead_options.keys()),
                               format_func=lambda x: lead_options.get(x, str(x)),
                               key="journey_sel")

        if st.button("Generate Lead Journey Report", key="gen_journey", type="primary"):
            with st.spinner("Generatig report..."):
                try:
                    data = api_client.get_lead_journey_report(TOKEN, sel_id)
                    st.session_state["journey_data"] = data
                    st.session_state["journey_lead_id"] = sel_id
                    st.success("Report generated!")
                except APIError as e:
                    err = str(e)
                    if "403" in err:
                        st.error("You can only generate reports for your assigned leads.")
                    elif "404" in err:
                        st.error("Lead not found.")
                    else:
                        st.error(f"Error: {e}")

        if st.session_state.get("journey_data") and st.session_state.get("journey_lead_id") == sel_id:
            data = st.session_state["journey_data"]
            metrics = data.get("metrics", {})
            by_type = metrics.get("by_event_type", {})

            st.markdown(f"### {data.get('lead_name', 'Lead')} — Journey Analysis")

            c1, c2 = st.columns([1, 2])
            with c1:
                st.markdown(f'<div class="metric-card"><div class="val">{metrics.get("total_events",0)}</div><div class="lbl">Timeline Events</div></div>', unsafe_allow_html=True)
            with c2:
                if by_type:
                    fig = px.bar(
                        x=list(by_type.keys()), y=list(by_type.values()),
                        labels={"x": "Event Type", "y": "Count"},
                        color=list(by_type.values()), color_continuous_scale="Blues",
                        title="Events by Type",
                    )
                    fig.update_layout(height=220, margin=dict(t=40,b=0,l=0,r=0), coloraxis_showscale=False)
                    st.plotly_chart(fig, use_container_width=True)

            show_narrative(data.get("narrative", ""))

            st.markdown("---")
            docx_b64 = data.get("docx_b64", "")
            if docx_b64:
                st.download_button(
                    label="Download Report (.docx)",
                    data=base64.b64decode(docx_b64),
                    file_name=f"lead_journey_{sel_id}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key="dl_journey_file",
                )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2: Periodic Leads Report
# ─────────────────────────────────────────────────────────────────────────────
with t_periodic:
    st.markdown("#### Periodic Leads Report")
    st.caption("Covers portfolio pipeline distribution AND individual lead journey highlights for the selected period.")

    col_scope, col_period = st.columns([1, 2])
    with col_scope:
        if ROLE == "sales_rep":
            scope_user_id = None
            st.info(f"Scope: **Your leads**")
        elif ROLE == "manager":
            scope_opts = {"All Team": None}
            scope_opts.update({u["name"]: u["id"] for u in sales_reps})
            chosen = st.selectbox("Scope", list(scope_opts.keys()), key="periodic_scope")
            scope_user_id = scope_opts[chosen]
        else:  # admin
            all_scope = {"Firm-Wide": None}
            all_scope.update({u["name"]: u["id"] for u in all_users})
            chosen = st.selectbox("Scope", list(all_scope.keys()), key="periodic_scope_admin")
            scope_user_id = all_scope[chosen]

    with col_period:
        sd, ed, period_label = date_range_selector("periodic")

    if st.button("Generate Periodic Leads Report", key="gen_periodic", type="primary"):
        with st.spinner("Gemini AI is analyzing your pipeline..."):
            try:
                data = api_client.get_periodic_leads_report(TOKEN, scope_user_id, sd, ed, period_label)
                st.session_state["periodic_data"] = data
                st.success("Report generated!")
            except APIError as e:
                st.error(f"Error: {e}")

    if st.session_state.get("periodic_data"):
        data = st.session_state["periodic_data"]
        metrics = data.get("metrics", {})
        st.markdown(f"### {metrics.get('target_name', '')} — {metrics.get('period_label', period_label)}")
        render_leads_metrics(metrics)
        show_narrative(data.get("narrative", ""))
        st.markdown("---")
        docx_b64 = data.get("docx_b64", "")
        if docx_b64:
            st.download_button(
                label="Download Report (.docx)",
                data=base64.b64decode(docx_b64),
                file_name="periodic_leads_report.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="dl_periodic_file",
            )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3: Individual Performance (Manager / Admin)
# ─────────────────────────────────────────────────────────────────────────────
if t_perf is not None:
    with t_perf:
        label = "Rep Performance Report" if ROLE == "manager" else "Individual Performance Review"
        st.markdown(f"#### {label}")
        st.caption("AI-generated individual performance review covering leads, conversions, appointments, and task execution.")

        if ROLE == "manager":
            perf_pool = sales_reps
            pool_label = "Select Sales Rep"
        else:  # admin
            perf_pool = all_users
            pool_label = "Select User (Rep or Manager)"

        if not perf_pool:
            st.warning("No reportable users found.")
        else:
            perf_opts = {u["id"]: f"{u['name']} ({u['role'].replace('_',' ').title()})" for u in perf_pool}
            sel_uid = st.selectbox(pool_label, list(perf_opts.keys()),
                                    format_func=lambda x: perf_opts.get(x, str(x)),
                                    key="perf_uid")
            psd, ped, p_period = date_range_selector("perf")

            if st.button("Generate Performance Report", key="gen_perf", type="primary"):
                with st.spinner("Gemini AI is compiling performance metrics..."):
                    try:
                        data = api_client.get_user_performance_report(TOKEN, sel_uid, psd, ped, p_period)
                        st.session_state["perf_data"] = data
                        st.session_state["perf_uid_sel"] = sel_uid
                        st.success("Report generated!")
                    except APIError as e:
                        err = str(e)
                        if "403" in err:
                            st.error("You can only view performance reports for your direct subordinates.")
                        else:
                            st.error(f"Error: {e}")

            if st.session_state.get("perf_data") and st.session_state.get("perf_uid_sel") == sel_uid:
                data = st.session_state["perf_data"]
                metrics = data.get("metrics", {})
                st.markdown(f"### {metrics.get('user_name','')} — {data.get('period_label', p_period)}")
                render_performance_metrics(metrics)
                show_narrative(data.get("narrative", ""))
                st.markdown("---")
                docx_b64 = data.get("docx_b64", "")
                if docx_b64:
                    st.download_button(
                        label="Download Report (.docx)",
                        data=base64.b64decode(docx_b64),
                        file_name=f"performance_{sel_uid}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="dl_perf_file",
                    )


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4: Team Digest (Manager / Admin)
# ─────────────────────────────────────────────────────────────────────────────
if t_team is not None:
    with t_team:
        st.markdown("#### Team Performance Digest")
        st.caption("Aggregate team metrics with AI analysis — comparative performance, bottlenecks, and recommendations.")

        col_tm1, col_tm2 = st.columns([1, 2])
        with col_tm1:
            mgr_filter = None
            if ROLE == "admin" and managers:
                mgr_opts = {"All Managers (Firm-Wide)": None}
                mgr_opts.update({m["name"]: m["id"] for m in managers})
                chosen_mgr = st.selectbox("Filter by Manager Team", list(mgr_opts.keys()), key="team_mgr")
                mgr_filter = mgr_opts[chosen_mgr]
            else:
                st.info("Scope: **Your team**")

        with col_tm2:
            tsd, ted, t_period = date_range_selector("team")

        if st.button("Generate Team Digest", key="gen_team", type="primary"):
            with st.spinner("Gemini AI is compiling team performance..."):
                try:
                    data = api_client.get_team_performance_report(TOKEN, tsd, ted, t_period, mgr_filter)
                    st.session_state["team_data"] = data
                    st.success("Report generated!")
                except APIError as e:
                    st.error(f"Error: {e}")

        if st.session_state.get("team_data"):
            data = st.session_state["team_data"]
            td = data.get("metrics", {})
            st.markdown(f"### {td.get('team_label','Team')} — {data.get('period_label', t_period)}")
            render_team_metrics(td)
            show_narrative(data.get("narrative", ""))
            st.markdown("---")
            docx_b64 = data.get("docx_b64", "")
            if docx_b64:
                st.download_button(
                    label="Download Report (.docx)",
                    data=base64.b64decode(docx_b64),
                    file_name="team_digest.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key="dl_team_file",
                )
