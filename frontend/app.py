import streamlit as st
import asyncio
from core.auth import require_login

# Ensure the user is logged in before redirecting
require_login()

# Redirect straight to the dashboard if authenticated
st.switch_page("pages/1_Dashboard.py")
