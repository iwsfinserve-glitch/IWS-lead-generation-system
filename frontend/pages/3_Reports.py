import streamlit as st
import pandas as pd
import time
from datetime import date, timedelta
from components.sidebar import render_sidebar
from components.report_engine import generate_chart_buffer, generate_docx_report

# ── st.set_page_config MUST be the very first Streamlit command ──
st.set_page_config(page_title="Reports", page_icon="", layout="wide")


# ── Page-level CSS: dotted background matching rest of app ──
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


# ── Page Header ──
st.markdown('<h1 style="display: inline; font-weight: 800;">Reports</h1><br>', unsafe_allow_html=True)

# ── Two main report tabs ──
# WHY st.tabs: Tabs share the same page script context and session_state.
# Unlike multipage navigation, switching tabs does NOT trigger a full rerun —
# Streamlit simply shows/hides the tab content. This means all widgets
# inside both tabs are always evaluated on every run, which is why we can
# safely store report results in session_state and they persist across
# tab switches.
tab1, tab2 = st.tabs(["Lead Journey Report", "Team Performance Digest"])

# ─────────────────────────────────────────────────────
# TAB 1: Lead Journey Report
# ─────────────────────────────────────────────────────
with tab1:
    st.subheader("Lead Journey Report")

    # Lead selector with name + company format
    selected_lead = st.selectbox(
        "Select Lead",
        options=[
            "Arjun Mehta - TechNova",
            "Priya Sharma - WealthEdge",
            "Rohan Das - AlphaCapital",
        ],
        key="journey_lead_select",
    )

    # Mock journey data keyed by lead name
    journey_data = {
        "Arjun Mehta - TechNova": {
            "first_contact": "2025-01-14",
            "touchpoints": 12,
            "objection": "pricing felt too high for the initial pilot",
            "resolution": "offered a phased rollout with a 15% discount on the first quarter",
            "stage": "Negotiation",
        },
        "Priya Sharma - WealthEdge": {
            "first_contact": "2025-02-03",
            "touchpoints": 8,
            "objection": "pricing was above their allocated budget for Q2",
            "resolution": "restructured the proposal into modular tiers so they could start small",
            "stage": "Proposal Sent",
        },
        "Rohan Das - AlphaCapital": {
            "first_contact": "2025-03-21",
            "touchpoints": 15,
            "objection": "pricing compared unfavourably against a competitor quote",
            "resolution": "provided a detailed ROI breakdown and extended payment terms to 90 days",
            "stage": "Closed Won",
        },
    }

    if st.button("Generate Report", key="gen_journey"):
        with st.spinner("Analysing lead history..."):
            time.sleep(2)
        # Build the mock AI summary referencing selected lead's data
        d = journey_data[selected_lead]
        name = selected_lead.split(" - ")[0]
        summary = (
            f"**Lead Journey Report — {selected_lead}**\n\n"
            f"First contact was recorded on **{d['first_contact']}**. "
            f"Since then, the sales team has logged **{d['touchpoints']} touchpoints** "
            f"across calls, emails, and in-person meetings.\n\n"
            f"The primary objection raised by {name} was that **{d['objection']}**. "
            f"The team addressed this by proposing a resolution: _{d['resolution']}_.\n\n"
            f"As of today, **{name}** is in the **{d['stage']}** stage of the pipeline. "
            f"Recommended next step: schedule a follow-up within 5 business days to "
            f"maintain momentum and close any remaining open items."
        )
        # WHY session_state: We store the generated report in session_state
        # so it survives Streamlit reruns. Without this, the report would
        # vanish the moment the user interacts with ANY widget on the page
        # (e.g., switching tabs, changing the dropdown).
        st.session_state["lead_journey_report"] = summary
        st.session_state["lead_journey_data"] = d

    # Persist report display across widget interactions
    if "lead_journey_report" in st.session_state:
        report_text = st.session_state["lead_journey_report"]
        d = st.session_state["lead_journey_data"]
        # Render as a styled blockquote for visual separation
        blockquote = "\n".join(f"> {line}" for line in report_text.split("\n"))
        st.markdown(blockquote)

        # Generate the chart for the DOCX export
        # This creates a simple touchpoints-by-stage bar chart
        journey_chart = generate_chart_buffer(
            labels=["Discovery", "Proposal", "Negotiation", "Follow-up"],
            values=[d["touchpoints"] // 3, d["touchpoints"] // 4,
                    d["touchpoints"] // 4, d["touchpoints"] - (d["touchpoints"] // 3 + d["touchpoints"] // 4 + d["touchpoints"] // 4)],
            title="Touchpoints by Stage",
            ylabel="Count",
        )

        # Build the DOCX with the chart embedded
        docx_bytes = generate_docx_report(
            title="Lead Journey Report",
            summary_text=report_text,
            chart_buffers=[("Touchpoints by Stage", journey_chart)],
        )

        st.download_button(
            label="📄 Export to DOCX",
            data=docx_bytes,
            file_name="lead_journey.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="dl_journey",
        )

# ─────────────────────────────────────────────────────
# TAB 2: Team Performance Digest
# ─────────────────────────────────────────────────────
with tab2:
    st.subheader("Team Performance Digest")

    # Sales rep selector
    selected_rep = st.selectbox(
        "Sales Rep",
        options=["Ananya Iyer", "Kabir Malhotra", "Sneha Rao"],
        key="perf_rep_select",
    )

    # ── Date Range Selector ──
    # WHY a selectbox + conditional date_inputs instead of just a raw date picker:
    # Sales reps almost always want a preset range ("last month", "last quarter").
    # A raw date picker forces them to remember and type exact dates every time.
    # The "Custom" option is the escape hatch for edge cases.
    range_option = st.selectbox(
        "Report Range",
        options=["Last Month", "Last Quarter", "Last Year", "Custom"],
        key="perf_range_option",
    )

    today = date.today()
    if range_option == "Last Month":
        # Go back one month: first day of previous month to last day of previous month
        first_of_this_month = today.replace(day=1)
        range_end = first_of_this_month - timedelta(days=1)
        range_start = range_end.replace(day=1)
    elif range_option == "Last Quarter":
        # Current quarter's first month, then go back 3 months
        current_quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        range_start = today.replace(month=current_quarter_start_month, day=1) - timedelta(days=90)
        range_start = range_start.replace(day=1)
        range_end = range_start.replace(month=range_start.month + 2, day=28)
    elif range_option == "Last Year":
        range_start = date(today.year - 1, 1, 1)
        range_end = date(today.year - 1, 12, 31)
    else:
        # Custom: show two date pickers side by side
        col_from, col_to = st.columns(2)
        with col_from:
            range_start = st.date_input("From", value=date(today.year, 1, 1), key="perf_from")
        with col_to:
            range_end = st.date_input("To", value=today, key="perf_to")

    # Show the computed range as a caption so the user always knows what period is selected
    st.caption(f"Reporting period: **{range_start}** to **{range_end}**")


    # Mock data per rep for both charts and the AI summary
    rep_data = {
        "Ananya Iyer": {
            "leads": [18, 22, 30, 25, 35, 28],
            "stages": [12, 8, 6, 10, 4],
            "top_month": "May",
            "conversion": "28%",
            "coaching": "Focus on shortening the proposal-to-negotiation cycle — current average is 11 days vs team target of 7.",
        },
        "Kabir Malhotra": {
            "leads": [15, 20, 18, 27, 24, 31],
            "stages": [10, 11, 5, 8, 6],
            "top_month": "June",
            "conversion": "22%",
            "coaching": "Increase discovery call depth — 40% of lost deals cite misaligned expectations set during initial outreach.",
        },
        "Sneha Rao": {
            "leads": [25, 28, 22, 30, 33, 40],
            "stages": [14, 9, 7, 12, 3],
            "top_month": "June",
            "conversion": "34%",
            "coaching": "Consider delegating mid-funnel follow-ups to free capacity for high-value negotiation calls.",
        },
    }

    if st.button("Generate Performance Report", key="gen_perf"):
        with st.spinner("Compiling metrics..."):
            time.sleep(2)

        rd = rep_data[selected_rep]

        # Chart 1 data: monthly leads contacted
        # WHY this DataFrame shape: st.bar_chart expects a DataFrame where
        # the index = x-axis labels and each column = a data series.
        # A single column named "Leads" gives us one monochrome bar group.
        chart1_df = pd.DataFrame(
            {"Leads": rd["leads"]},
            index=["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
        )

        # Chart 2 data: deal stage distribution
        chart2_df = pd.DataFrame(
            {"Count": rd["stages"]},
            index=["Qualified", "Proposal", "Negotiation", "Closed Won", "Closed Lost"],
        )

        # AI summary text referencing the selected rep
        summary_text = (
            f"{selected_rep} contacted the most leads in **{rd['top_month']}**, "
            f"achieving an overall conversion rate of **{rd['conversion']}** for the selected period. "
            f"Performance has been trending upward over the last three months. "
            f"**Coaching recommendation:** {rd['coaching']}"
        )

        # Store everything in session state for persistence
        st.session_state["perf_chart1"] = chart1_df
        st.session_state["perf_chart2"] = chart2_df
        st.session_state["perf_summary"] = summary_text
        st.session_state["perf_rep_name"] = selected_rep

    # Display persisted report content
    if "perf_chart1" in st.session_state:
        chart1_df = st.session_state["perf_chart1"]
        chart2_df = st.session_state["perf_chart2"]
        summary_text = st.session_state["perf_summary"]
        rep_name = st.session_state["perf_rep_name"]

        st.caption("Monthly Leads Contacted")
        st.bar_chart(chart1_df, color="#262626")

        st.caption("Deal Stage Distribution")
        st.bar_chart(chart2_df, color="#888888")

        # AI-generated summary block
        st.info(summary_text)

        # ── Build the DOCX with BOTH charts embedded ──
        # Generate Matplotlib versions of both charts for the Word doc
        chart1_buf = generate_chart_buffer(
            labels=chart1_df.index.tolist(),
            values=chart1_df["Leads"].tolist(),
            title="Monthly Leads Contacted",
            ylabel="Leads",
        )
        chart2_buf = generate_chart_buffer(
            labels=chart2_df.index.tolist(),
            values=chart2_df["Count"].tolist(),
            title="Deal Stage Distribution",
            ylabel="Count",
        )

        docx_bytes = generate_docx_report(
            title=f"Performance Digest — {rep_name}",
            summary_text=summary_text,
            chart_buffers=[
                ("Monthly Leads Contacted", chart1_buf),
                ("Deal Stage Distribution", chart2_buf),
            ],
        )

        st.download_button(
            label="📄 Export to DOCX",
            data=docx_bytes,
            file_name="performance_digest.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="dl_perf",
        )
