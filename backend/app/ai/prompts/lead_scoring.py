# backend/app/ai/prompts/lead_scoring.py
"""
Lead-scoring prompt template and context formatter.

Keeping prompt text in a dedicated module means:
- Prompt changes never touch business logic or route files.
- The prompt can be unit-tested in isolation.
- Easy A/B swap: replace build_lead_scoring_context(), keep LeadScoringFeature.
"""

LEAD_SCORING_PROMPT_TEMPLATE = """\
You are an expert financial advisory and wealth management analyst for a privately held wealth management and financial services firm in India.
Your task is to score a sales lead based on the structured data below.

## Domain Context & Business Model
- We are NOT a bank and NOT a lending institution. We provide relationship-driven wealth advisory, mutual fund distribution, Portfolio Management Services (PMS), Alternative Investment Funds (AIF), equity broking, insurance, bonds, and family office services.
- Look for signals of high-net-worth liquidity, goal-based investment planning (retirement, tax-efficiency, education, wealth preservation), mutual fund SIP interest, portfolio restructuring, and readiness for KYC/PAN/AMFI compliance.

## Scoring criteria
- 80-100 (hot): High engagement, strong investment surplus/liquidity signals, upcoming consultation meetings, active interest in PMS/AIF/SIP allocation
- 50-79  (warm): Moderate engagement, some interaction history, exploring mutual funds or financial planning options
- 0-49   (cold): Little or no engagement, stale data, low investment intent, or explicit disqualification/disengagement

## Lead profile
{lead_profile}

## Required output
Return a single JSON object. Do NOT wrap it in markdown code fences. Example shape:
{{
  "score": 85,
  "label": "hot",
  "reasoning": "High-intent HNI profile inquiring about a ₹1.5 Cr PMS allocation. Active engagement across multiple phone calls and a scheduled portfolio review meeting indicate serious long-term wealth management intent.",
  "key_signals": ["Inquiry for ₹1.5 Cr Portfolio Management Services (PMS)", "Scheduled portfolio review and asset allocation meeting", "High liquidity and readiness for SEBI/AMFI KYC verification"],
  "suggested_next_action": "Prepare customized 5-year XIRR/CAGR performance projections and share the PMS strategy brochure."
}}

Rules:
- score must be an integer 0-100.
- label must be exactly "hot", "warm", or "cold" (lowercase).
- key_signals: 2-5 bullet strings, most important first.
- reasoning: 2-4 sentences max; factual, no filler.
- suggested_next_action: one actionable sentence for the assigned financial advisor.
"""


def build_lead_scoring_context(data: dict) -> str:
    """Format a lead context dict into the final prompt string.

    Expected keys in `data` (all optional — missing values are shown as 'N/A'):
        lead_id, status, source_name, days_since_created,
        assigned_rep_name, interaction_count, interaction_breakdown,
        last_interaction_date, interaction_notes_summary,
        appointment_count, appointment_outcomes
    """
    def _v(key: str, default: str = "N/A") -> str:
        val = data.get(key)
        return str(val) if val is not None else default

    # Format interaction breakdown (dict of type→count)
    breakdown = data.get("interaction_breakdown", {})
    breakdown_str = (
        ", ".join(f"{k}: {v}" for k, v in breakdown.items())
        if breakdown
        else "none"
    )

    # Format appointment outcomes (list of strings)
    outcomes = data.get("appointment_outcomes", [])
    outcomes_str = "; ".join(outcomes) if outcomes else "none"

    lead_profile = (
        f"- Lead ID: {_v('lead_id')}\n"
        f"- Current status: {_v('status')}\n"
        f"- Lead source: {_v('source_name')}\n"
        f"- Days since created: {_v('days_since_created')}\n"
        f"- Assigned rep: {_v('assigned_rep_name')}\n"
        f"- Total interactions: {_v('interaction_count', '0')}\n"
        f"- Interaction breakdown: {breakdown_str}\n"
        f"- Most recent interaction: {_v('last_interaction_date')}\n"
        f"- Interaction notes summary: {_v('interaction_notes_summary')}\n"
        f"- Total appointments: {_v('appointment_count', '0')}\n"
        f"- Appointment outcomes: {outcomes_str}\n"
    )

    return LEAD_SCORING_PROMPT_TEMPLATE.format(lead_profile=lead_profile)
