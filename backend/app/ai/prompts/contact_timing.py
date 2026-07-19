# backend/app/ai/prompts/contact_timing.py
"""
Contact-timing prompt template and context formatter.

Gemini is asked to identify the best days and time window to contact a lead
based on patterns in their interaction history (response rates, appointment
times, timeline event timestamps).

IMPORTANT: This prompt is only called when the sparse-data guard in
ContactTimingFeature.run() confirms there are enough interactions.
Never ask Gemini to invent a window from an empty history.
"""

CONTACT_TIMING_PROMPT_TEMPLATE = """\
You are a CRM analyst specialising in contact-time optimisation for a \
privately held wealth management and financial advisory firm in India.

Analyse the interaction history below and determine the best days and time \
window to contact this lead for financial planning or portfolio reviews.

## Lead interaction history
{interaction_history}

## Instructions
- Look for patterns: which days and times do interactions tend to occur? \
Which interactions had follow-ups or generated responses?
- Consider scheduled portfolio review or consultation appointment times as strong signals (the lead agreed to them).
- Keep in mind market hours (09:15–15:30 IST) or post-work hours when salaried professionals and HNIs prefer financial reviews.
- If the data clearly favours certain days/windows, state them with \
"medium" or "high" confidence.
- If patterns exist but are weak (e.g. only 3-4 interactions spread across \
all days), use "low" confidence and set suggested_window to null.
- suggested_days: list the day names (e.g. "Monday", "Thursday") that \
appear most often in successful or recent interactions. Return 1-3 days.
- suggested_window: a concise time range string like "10:00–12:00" or \
"16:00–18:00" in 24-hour format (IST). Set to null if insufficient data.

## Required output
Return a single JSON object. Do NOT wrap it in markdown code fences.
{{
  "has_sufficient_data": true,
  "suggested_days": ["Tuesday", "Thursday"],
  "suggested_window": "10:00–12:00",
  "confidence": "medium",
  "reasoning": "Three of five interactions occurred on Tuesday mornings during market hours. \
One portfolio review appointment was booked for a Thursday 11 AM slot."
}}

Rules:
- has_sufficient_data must be true (you are only called when data exists).
- confidence must be exactly "low", "medium", or "high".
- suggested_days must be a list of 1-3 day name strings.
- suggested_window: string or null.
- reasoning: 2-3 sentences, factual, no filler.
"""


def build_contact_timing_context(data: dict) -> str:
    """Format the lead's interaction timestamps into the final prompt string.

    Expected keys in `data`:
        interaction_count      int
        interaction_events     list[dict] with keys: event_type, day_name,
                               time_str (HH:MM or None), date_str
        appointment_events     list[dict] with keys: title, day_name,
                               time_str, date_str
    """
    events = data.get("interaction_events", [])
    appointments = data.get("appointment_events", [])

    lines: list[str] = []

    if events:
        lines.append("### Timeline interactions")
        for ev in events:
            time_part = f" at {ev['time_str']}" if ev.get("time_str") else ""
            lines.append(
                f"- [{ev['date_str']}] {ev['day_name']}{time_part} — {ev['event_type']}"
            )

    if appointments:
        lines.append("\n### Booked appointments (strong signals)")
        for appt in appointments:
            time_part = f" at {appt['time_str']}" if appt.get("time_str") else ""
            lines.append(
                f"- [{appt['date_str']}] {appt['day_name']}{time_part} — {appt['title']}"
            )

    if not lines:
        lines.append("No interaction data available.")

    interaction_history = "\n".join(lines)
    return CONTACT_TIMING_PROMPT_TEMPLATE.format(
        interaction_history=interaction_history
    )
