# backend/app/ai/prompts/client_classification.py
"""
Client-classification prompt template and context formatter.

Gemini is asked to classify a lead as 'hni', 'professional', or 'retail'
by holistically weighing all available signals: profession, income source,
stated goals, investable amounts mentioned, and the full body of interaction
notes recorded by the sales rep.

The rubric is calibrated for Goa, India — a market with a distinct mix of
hospitality entrepreneurs, government/defence professionals, NRI returnees,
fishing & agriculture families, and a growing IT/startup population.

IMPORTANT: This prompt is only called after the sparse-data guard in
ClientClassificationFeature.run() confirms there are enough substantive
notes to reason from. Never ask Gemini to classify from an empty history.
"""

# ── Rubric ────────────────────────────────────────────────────────────────────
# This rubric is deliberately qualitative (per user feedback) so that Gemini
# can weigh profession, income source, stated goals, and interaction signals
# holistically rather than applying a hard numeric cutoff.
#
# Goa-specific calibration:
#   HNI signals strong in Goa: hotel/resort ownership, Goa-origin NRI returnees
#     with overseas savings, mining/real estate legacy wealth, casino operators,
#     established builders and contractors.
#   Professional signals: government officers (IAS/IPS/KAS/defence), doctors at
#     Goa Medical College / private hospitals, lawyers, senior IT/MNC employees
#     in Vasco/Margao/Panaji, principals and college staff.
#   Retail signals: daily-wage workers, fishermen, small shopkeepers, junior
#     government staff, contract laborers, first-time investors with minimal
#     surplus.

CLIENT_CLASSIFICATION_PROMPT_TEMPLATE = """\
You are a senior wealth management analyst at a privately held financial \
advisory firm headquartered in Goa, India. You serve the full spectrum of \
clients — from first-time retail investors to ultra-high-net-worth families \
with legacy wealth from Goa's hospitality, mining, and real-estate sectors.

Your task is to classify the lead/client below into exactly ONE of three tiers:

  hni          — High Net Worth Individual (very high financial capacity)
  professional — High-income salaried or self-employed specialist (solid capacity)
  retail       — Salaried worker or early-stage investor (modest capacity)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## CLASSIFICATION RUBRIC (Goa, India context)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### HNI
Holistically weigh ALL of the following signals — no single signal is required,
but the combined picture must clearly suggest very high investable capacity:
- Business ownership: hotels, resorts, mining interests, construction, real estate
  development, casinos, large trading businesses, export/import operations.
- NRI/returnee with overseas savings or foreign remittances.
- Legacy family wealth or substantial ancestral property mentioned.
- Stated investable surplus clearly in the Rs 50 lakh to crore-plus range
  (or equivalent in foreign currency for NRIs).
- Goals: bespoke portfolio management, PMS/AIF allocation, tax-efficient
  succession planning, wealth preservation, family office discussions,
  offshore/GIFT City investment enquiry.
- Profession signals: business owner, MD/CEO/director of a company,
  senior politician or industrialist, large landlord/property developer.

### PROFESSIONAL
- High-income salaried or self-employed specialist with consistent,
  predictable earnings clearly above the Goa median.
- Examples: government officer (IAS, IPS, KAS, defence officer), doctor /
  specialist at a hospital or clinic, lawyer / CA / architect, senior manager
  or department head at an MNC/IT firm, principal/dean, established chartered
  accountant or financial planner.
- Stated investable surplus in the Rs 5 lakh to Rs 50 lakh range per year,
  or a lump-sum of that order being discussed.
- Goals: retirement planning, aggressive mutual fund SIP, ELSS/tax saving,
  children's education fund, buying a property with investment intent,
  balanced growth portfolio.

### RETAIL
- Salaried employee with modest earnings, small business owner at early stage,
  or someone exploring investments for the first time.
- Examples: shop assistant, fisherman, farmer, junior government staff,
  contract/daily-wage worker, small-vendor owner, private-school teacher
  at a low-income institution.
- Stated investable surplus is small (e.g. a few thousand rupees per month),
  or unclear/not mentioned with no high-income signals.
- Goals: basic SIP of small amounts, emergency fund, FD vs SIP comparison,
  repaying debt, starting an LIC/insurance plan.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## LEAD PROFILE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{lead_profile}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## ACCUMULATED INTERACTION NOTES
(All notes recorded by sales reps over the client relationship, oldest first)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{interaction_notes}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## INSTRUCTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Holistically weigh every signal — profession, stated investable amount,
   income source, goals, lifestyle cues, and the overall tone and detail of
   the interaction notes.
2. Do NOT fixate on a single data point. A doctor in Goa with modest savings
   is 'professional', not 'hni'. A resort owner with limited notes but clear
   business context can still be 'hni'.
3. If the data is contradictory (e.g. luxury lifestyle cues but explicitly
   small investment amounts), lean toward the more conservative tier and
   report low confidence with clear reasoning.
4. Key indicators must be verbatim quotes or very close paraphrases from
   the notes/profile above — do not invent or extrapolate details.
5. Reasoning must be concise (2-3 sentences) and factual.

## Required output
Return a single JSON object. Do NOT wrap it in markdown code fences.
{{
  "has_sufficient_data": true,
  "classification": "professional",
  "confidence": "high",
  "reasoning": "Lead is a senior cardiologist at a private hospital in Panaji with a stated monthly surplus of Rs 80,000. Goals include PMS allocation and retirement planning. The volume and specificity of notes strongly support the professional tier.",
  "key_indicators": [
    "Senior cardiologist at Panaji private hospital",
    "Monthly surplus approx Rs 80,000 mentioned in call notes",
    "Explicitly interested in PMS and retirement portfolio"
  ]
}}

Rules:
- has_sufficient_data must be true (you are only called when data exists).
- classification must be exactly "hni", "professional", or "retail".
- confidence must be exactly "low", "medium", or "high".
- key_indicators: 2-5 short strings; only use information present in the notes.
- reasoning: 2-3 sentences; specific, no filler.
"""


def build_client_classification_context(data: dict) -> str:
    """Format the lead profile and aggregated notes into the final prompt string.

    Expected keys in ``data``:
        lead_name            str
        profession           str | None
        address              str | None
        status               str
        source_name          str | None
        days_since_created   int
        assigned_rep_name    str | None
        note_entries         list[dict]  — [{date_str, note_text}] oldest-first
        appointment_count    int
        appointment_outcomes list[str]
    """
    def _v(key: str, default: str = "N/A") -> str:
        val = data.get(key)
        return str(val) if val is not None else default

    # ── Lead profile block ────────────────────────────────────────────
    outcomes = data.get("appointment_outcomes", [])
    outcomes_str = "; ".join(outcomes) if outcomes else "none"

    lead_profile = (
        f"- Name: {_v('lead_name')}\n"
        f"- Profession: {_v('profession')}\n"
        f"- Address / Location: {_v('address')}\n"
        f"- Lead source: {_v('source_name')}\n"
        f"- Current CRM status: {_v('status')}\n"
        f"- Days in CRM: {_v('days_since_created', '0')}\n"
        f"- Assigned advisor: {_v('assigned_rep_name')}\n"
        f"- Total appointments: {_v('appointment_count', '0')}\n"
        f"- Appointment context: {outcomes_str}\n"
    )

    # ── Interaction notes block ───────────────────────────────────────
    note_entries = data.get("note_entries", [])
    if note_entries:
        note_lines = [
            f"[{entry['date_str']}] {entry['note_text']}"
            for entry in note_entries
        ]
        interaction_notes = "\n".join(note_lines)
    else:
        interaction_notes = "No notes recorded."

    return CLIENT_CLASSIFICATION_PROMPT_TEMPLATE.format(
        lead_profile=lead_profile,
        interaction_notes=interaction_notes,
    )
