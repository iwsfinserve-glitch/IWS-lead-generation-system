"""
auth_guard.py — Simple authentication check for all pages.

Call require_login() at the top of every page, AFTER st.set_page_config().
If the user is not logged in, it shows a message and stops the page.
"""

import streamlit as st


def require_login():
    """Check if user is logged in. If not, show login prompt and stop."""
    if "token" not in st.session_state or not st.session_state.token:
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
        st.warning("Please log in to access this page.")
        st.page_link("pages/0_Login.py", label="Go to Login", icon="🔐")
        st.stop()
