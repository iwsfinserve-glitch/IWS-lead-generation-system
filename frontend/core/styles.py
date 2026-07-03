"""
styles.py — Centralized CSS injection for the entire Streamlit frontend.

Instead of copy-pasting <style> blocks into every page file, each page
calls one of these helper functions to inject the exact CSS it needs.

Usage:
    from core.styles import inject_global_styles
    inject_global_styles()          # background only (Login, Reports, User Details)
    inject_global_styles(
        drawer=True,                # modal dialog as right-side drawer
        overlay_cards=True,         # clickable card overlay hack
        user_cards=True,            # user card overlay hack (Dashboard only)
        metric_card=True,           # .metric-card class (User Details)
    )
"""

import streamlit as st

# ── Base Styles ──────────────────────────────────────────────────────
# The dotted background shared by every single page.
_BASE_CSS = """
.stApp {
    background-color: #fefefe;
    background-image:
        radial-gradient(circle, rgba(20,20,20,0.1) .8px, transparent .3px);
    background-size: 10px 10px;
}
"""

# ── Drawer Modal ─────────────────────────────────────────────────────
# Converts the default Streamlit st.dialog into a right-side drawer panel.
_DRAWER_CSS = """
/* Blur + darken the backdrop behind the dialog */
div[data-testid="stModal"] > div:first-child {
    background: rgba(0, 0, 0, 0.5) !important;
    backdrop-filter: blur(4px);
}
/* Reposition the dialog as a right-side drawer */
div[data-testid="stModal"] div[role="dialog"] {
    position: fixed !important;
    right: 0 !important;
    top: 0 !important;
    left: auto !important;
    width: 420px !important;
    max-width: 420px !important;
    height: 100vh !important;
    max-height: 100vh !important;
    border-radius: 0 !important;
    margin: 0 !important;
    transform: none !important;
    padding: 24px !important;
}
"""

# ── Overlay Card Hack ────────────────────────────────────────────────
# Makes an HTML card clickable by overlaying a transparent Streamlit button
# on top of it.  The `margin-bottom` value should match the card height.
_OVERLAY_CARD_CSS = """
div.element-container:has(.overlay-trigger) {
    margin-bottom: -85px;
    position: relative;
}
div.element-container:has(.overlay-trigger) + div.element-container {
    opacity: 0;
    position: relative;
    z-index: 10;
}
div.element-container:has(.overlay-trigger) + div.element-container button {
    height: 75px !important;
    width: 100% !important;
    cursor: pointer;
}
.overlay-trigger:hover {
    border-color: #555;
    background-color: #f9f9f9;
    transform: translateY(-5px);
}
"""

# ── User Card Overlay Hack (Dashboard only) ─────────────────────────
# Similar to the overlay card hack but targets user cards which use
# st.columns (stLayoutWrapper) for the action buttons.
_USER_CARD_CSS = """
/* --- User Cards Overlay Hack --- */
div.element-container:has(.user-card-html) {
    margin-bottom: -87px;
    position: relative;
}
/* Target the stLayoutWrapper sibling (which holds st.columns) */
div.element-container:has(.user-card-html) + div[data-testid="stLayoutWrapper"] {
    opacity: 0 !important;
    position: relative;
    z-index: 10;
    margin-bottom: 12px;
}
div.element-container:has(.user-card-html) + div[data-testid="stLayoutWrapper"] button {
    height: 75px !important;
    width: 100% !important;
    cursor: pointer;
}
/* Target a plain element-container sibling (manager view with single button) */
div.element-container:has(.user-card-html) + div.element-container {
    opacity: 0 !important;
    position: relative;
    z-index: 10;
    margin-bottom: 12px;
}
div.element-container:has(.user-card-html) + div.element-container button {
    height: 75px !important;
    width: 100% !important;
    cursor: pointer;
}
"""

# ── Metric Card Class ────────────────────────────────────────────────
_METRIC_CARD_CSS = """
.metric-card {
    border: 1px solid rgba(54,57,62,0.3);
    border-radius: 8px;
    padding: 20px;
    text-align: center;
    background-color: white;
}
"""


def inject_global_styles(
    *,
    drawer: bool = False,
    overlay_cards: bool = False,
    user_cards: bool = False,
    metric_card: bool = False,
) -> None:
    """Inject global CSS into the current Streamlit page.

    Args:
        drawer:        Include the right-side modal drawer CSS.
        overlay_cards: Include the overlay-trigger clickable card CSS.
        user_cards:    Include the user-card overlay CSS (Dashboard).
        metric_card:   Include the .metric-card utility class.
    """
    parts = [_BASE_CSS]
    if drawer:
        parts.append(_DRAWER_CSS)
    if overlay_cards:
        parts.append(_OVERLAY_CARD_CSS)
    if user_cards:
        parts.append(_USER_CARD_CSS)
    if metric_card:
        parts.append(_METRIC_CARD_CSS)

    css = "\n".join(parts)
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
