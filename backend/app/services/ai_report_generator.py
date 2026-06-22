"""
AI Report Generator — Gemini-powered narrative reports as .docx downloads.

Provides two report types:
1. Lead Journey Report — narrative from a lead's timeline events
2. Team Performance Report — digest from aggregated user metrics

Both use Google's Gemini API for AI summarisation, then render
the output into a .docx file via python-docx.
"""

import io
import json
import logging

from google import genai
from docx import Document

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_client() -> genai.Client:
    """Get a configured Gemini client."""
    if not settings.GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set in .env. "
            "Get one from https://aistudio.google.com/apikey"
        )
    return genai.Client(api_key=settings.GEMINI_API_KEY)


async def generate_lead_journey_report(timeline_data: list[dict], lead_name: str) -> str:
    """Send timeline events to Gemini and get a narrative summary.

    Args:
        timeline_data: List of dicts with event_type, metadata, created_at.
        lead_name: Name of the lead for context.

    Returns:
        A multi-paragraph narrative string from Gemini.
    """
    prompt = f"""You are a CRM analytics assistant. Analyze the following timeline of events
for a lead named "{lead_name}" and produce a professional narrative report.

The report should include:
1. A brief overview of the lead's journey
2. Key milestones and status changes
3. Communication and engagement summary
4. Recommendations for next steps

Timeline data (JSON):
{json.dumps(timeline_data, indent=2)}

Write the report in clear, professional English. Use paragraphs, not bullet points.
"""

    try:
        client = _get_client()
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return response.text
    except Exception:
        logger.exception("Gemini API call failed for lead journey report")
        return (
            f"AI report generation failed. Raw timeline data for {lead_name}:\n\n"
            + json.dumps(timeline_data, indent=2)
        )


async def generate_team_performance_report(metrics: dict) -> str:
    """Send team metrics to Gemini and get a performance digest.

    Args:
        metrics: Dict of {user_name: {role, assigned_leads, appointments, tasks_completed}}.

    Returns:
        A multi-paragraph performance digest from Gemini.
    """
    prompt = f"""You are a CRM analytics assistant. Analyze the following team performance
metrics and produce a professional performance digest report.

The report should include:
1. Team overview and composition
2. Individual performance highlights
3. Areas of concern or bottlenecks
4. Actionable recommendations for management

Team metrics (JSON):
{json.dumps(metrics, indent=2)}

Write the report in clear, professional English. Use paragraphs, not bullet points.
"""

    try:
        client = _get_client()
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return response.text
    except Exception:
        logger.exception("Gemini API call failed for team performance report")
        return (
            "AI report generation failed. Raw metrics:\n\n"
            + json.dumps(metrics, indent=2)
        )


def build_docx_report(title: str, body_text: str) -> io.BytesIO:
    """Render a title + body into a .docx file and return as a BytesIO buffer.

    Args:
        title: The report title (rendered as Heading 1).
        body_text: The AI-generated narrative (split into paragraphs).

    Returns:
        A BytesIO buffer containing the .docx file, ready for StreamingResponse.
    """
    doc = Document()
    doc.add_heading(title, level=1)

    for paragraph in body_text.strip().split("\n\n"):
        cleaned = paragraph.strip()
        if cleaned:
            doc.add_paragraph(cleaned)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer
