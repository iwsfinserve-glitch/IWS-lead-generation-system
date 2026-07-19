# backend/app/ai/features/report_generation.py
"""
ReportGenerationFeature — AI-powered narrative report generation.

All features use the centralised AIClient (Gemini) with wealth management
and financial advisory domain context baked into every prompt.

Features:
    LeadJourneyFeature         — Lead journey narrative (full timeline)
    PeriodicLeadsReportFeature — Combined portfolio overview + lead journeys
                                 across a date range
    UserPerformanceFeature     — Individual sales rep / manager performance digest
    TeamPerformanceFeature     — Aggregate team performance digest
"""

import json
import logging
from collections import Counter

from app.ai.base import BaseAIFeature
from app.ai.client import AIClient, get_ai_client
from app.ai.schemas import ReportText

logger = logging.getLogger(__name__)


# ── Prompt builders ───────────────────────────────────────────────────────────

def _lead_journey_prompt(timeline_data: list[dict], lead_name: str) -> str:
    return f"""You are a senior wealth management advisor at a private financial services firm in India.
Analyze the following interaction timeline for the prospective client named "{lead_name}" and produce a
professional advisory report.

The report must include:
1. A brief overview of the client's wealth management journey (HNI profile, stated goals, product interest)
2. Key engagement milestones and portfolio status changes
3. Communication and meeting engagement summary
4. Risk signals or objections raised
5. Concrete next steps for the advisor (e.g., PMS onboarding, AIF mandate, SIP escalation, KYC follow-up)

Timeline data (JSON):
{json.dumps(timeline_data, indent=2)}

Write in clear, professional financial advisory English. Use paragraphs, not bullet points.
Assume the reader is a relationship manager reviewing the account.
"""


def _periodic_leads_prompt(summary: dict, period_label: str, target_name: str) -> str:
    leads = summary.get("leads", [])
    by_status = summary.get("by_status", {})
    by_source = summary.get("by_source", {})
    total = summary.get("total_leads", 0)
    converted = by_status.get("converted_to_investor", 0)
    conversion_rate = round(converted / total * 100, 1) if total > 0 else 0

    leads_detail = json.dumps(leads[:20], indent=2)  # limit payload size

    return f"""You are a senior wealth management analytics professional at a private financial services firm in India.
Generate a comprehensive periodic leads portfolio and journey report for: {target_name}
Period: {period_label}

The report must include:
1. Executive Summary — total pipeline size, acquisition channels, conversion performance
2. Portfolio Distribution — breakdown by pipeline stage (New, In Progress, Potential, Converted, Non-Potential)
3. Lead Journey Highlights — key interactions, status changes, and engagement quality across leads in this period
4. Top Performing Leads — 2-3 leads with the strongest engagement or conversion signals
5. Leads Requiring Attention — 2-3 leads at risk (cold, stalled, objections raised)
6. Wealth Management Insights — patterns in investment product interest (PMS, SIP, AIF, MF), ticket sizes, and risk appetite
7. Recommended Actions — specific next steps to improve pipeline conversion for this period

Pipeline data:
- Total leads: {total}
- By stage: {json.dumps(by_status)}
- By source: {json.dumps(by_source)}
- Conversion rate: {conversion_rate}%

Individual lead details:
{leads_detail}

Write in clear, professional English with a wealth management advisory perspective.
Use paragraphs and clear section headings (not raw bullet points).
"""


def _user_performance_prompt(metrics: dict, period_label: str, user_name: str, user_role: str) -> str:
    return f"""You are a wealth management business head evaluating team performance at a private financial services firm in India.
Generate a detailed individual performance review for: {user_name} ({user_role.replace('_', ' ').title()})
Period: {period_label}

The report must include:
1. Performance Overview — key headline metrics and overall assessment
2. Lead Pipeline Management — leads handled, conversion efficiency, pipeline movement
3. Client Engagement Quality — interaction volume, appointment execution, follow-up consistency
4. Task & Operational Execution — task completion rate, responsiveness, SLA adherence
5. Strengths — specific areas where the advisor is excelling in wealth advisory activities
6. Development Areas — gaps in client engagement, pipeline conversion, or wealth product knowledge
7. Specific Recommendations — actionable coaching points for the next period (PMS mandates, SIP upsells, referral generation)

Performance metrics (JSON):
{json.dumps(metrics, indent=2)}

Write in a professional, balanced performance review tone.
Use clear section headings and paragraphs (not raw bullet points).
Be data-driven and specific, referencing the actual numbers provided.
"""


def _team_performance_prompt(metrics: dict) -> str:
    return f"""You are a wealth management business head at a private financial services firm in India.
Analyze the following team performance metrics and produce a professional performance digest.

The report must include:
1. Team Overview — composition, aggregate pipeline size and activity levels
2. Individual Performance Highlights — who is leading in conversions, engagement, and AUM mandates
3. Comparative Analysis — relative performance ranking among team members
4. Areas of Concern — advisors or segments with low conversion, stalled pipelines, or poor engagement
5. Revenue & Business Impact — estimated AUM impact from conversions (if data available)
6. Actionable Recommendations — specific management interventions, coaching priorities, and process improvements
7. Team Goals for Next Period — suggested targets aligned with wealth management advisory KPIs

Team metrics (JSON):
{json.dumps(metrics, indent=2)}

Write in clear, professional English for a senior management audience.
Use section headings and paragraphs (not raw bullet points).
"""


# ── Feature classes ───────────────────────────────────────────────────────────

class LeadJourneyFeature(BaseAIFeature[dict, ReportText]):
    """Generates a lead journey narrative report."""

    feature_name = "lead_journey_report"
    response_schema = ReportText

    def build_prompt(self, context: dict) -> str:  # type: ignore[override]
        return _lead_journey_prompt(
            context["timeline_data"], context["lead_name"]
        )

    async def run(self, context: dict, entity_id: int | str = "") -> ReportText:  # type: ignore[override]
        prompt = self.build_prompt(context)
        return await self.client.generate(
            prompt=prompt,
            response_schema=self.response_schema,
            feature_name=self.feature_name,
            entity_id=entity_id,
            plain_text=True,
        )


class PeriodicLeadsReportFeature(BaseAIFeature[dict, ReportText]):
    """Generates a combined portfolio overview + lead journeys report for a period."""

    feature_name = "periodic_leads_report"
    response_schema = ReportText

    def build_prompt(self, context: dict) -> str:  # type: ignore[override]
        return _periodic_leads_prompt(
            context["summary"],
            context["period_label"],
            context["target_name"],
        )

    async def run(self, context: dict, entity_id: int | str = "") -> ReportText:  # type: ignore[override]
        prompt = self.build_prompt(context)
        return await self.client.generate(
            prompt=prompt,
            response_schema=self.response_schema,
            feature_name=self.feature_name,
            entity_id=entity_id,
            plain_text=True,
        )


class UserPerformanceReportFeature(BaseAIFeature[dict, ReportText]):
    """Generates an individual performance report for a sales rep or manager."""

    feature_name = "user_performance_report"
    response_schema = ReportText

    def build_prompt(self, context: dict) -> str:  # type: ignore[override]
        return _user_performance_prompt(
            context["metrics"],
            context["period_label"],
            context["user_name"],
            context["user_role"],
        )

    async def run(self, context: dict, entity_id: int | str = "") -> ReportText:  # type: ignore[override]
        prompt = self.build_prompt(context)
        return await self.client.generate(
            prompt=prompt,
            response_schema=self.response_schema,
            feature_name=self.feature_name,
            entity_id=entity_id,
            plain_text=True,
        )


class TeamPerformanceFeature(BaseAIFeature[dict, ReportText]):
    """Generates a team performance digest report."""

    feature_name = "team_performance_report"
    response_schema = ReportText

    def build_prompt(self, context: dict) -> str:  # type: ignore[override]
        return _team_performance_prompt(context["metrics"])

    async def run(self, context: dict, entity_id: int | str = "") -> ReportText:  # type: ignore[override]
        prompt = self.build_prompt(context)
        return await self.client.generate(
            prompt=prompt,
            response_schema=self.response_schema,
            feature_name=self.feature_name,
            entity_id=entity_id,
            plain_text=True,
        )
