"""
constants.py — Shared UI constants used across the Streamlit frontend.

Consolidates lead status display names, API values, color configs,
and filter sets that were previously defined in modals.py and imported
from there by cards.py, pages, etc.
"""

# Human-readable display names keyed by API status value.
STATUS_DISPLAY = {
    "unassigned": "Unassigned",
    "in_progress": "In Progress",
    "potential": "Potential",
    "non_potential": "Non-Potential",
    "converted_to_investor": "Converted",
    "existing_investor": "Existing Investor",
}

# Ordered list of API status values (for dropdowns).
STATUS_OPTIONS_API = [
    "unassigned", "in_progress", "potential", "non_potential",
    "converted_to_investor", "existing_investor",
]

# Display labels in the same order as STATUS_OPTIONS_API.
STATUS_OPTIONS_DISPLAY = [STATUS_DISPLAY[s] for s in STATUS_OPTIONS_API]

# Card badge config: abbreviation + background color per status.
STATUS_CONFIG = {
    "unassigned":    {"abbr": "U",  "bg": "#607D8B"},   # blue-grey — awaiting assignment
    "in_progress":   {"abbr": "IP", "bg": "#FFC107"},
    "potential":     {"abbr": "P",  "bg": "#4CAF50"},
    "non_potential": {"abbr": "NP", "bg": "Red"},
    "converted_to_investor": {"abbr": "C", "bg": "#2196F3"},
    "existing_investor": {"abbr": "EI", "bg": "#6A0DAD"},
}

# Statuses considered "active" (i.e. not converted/investor).
ACTIVE_STATUSES = {"unassigned", "in_progress", "potential", "non_potential"}
