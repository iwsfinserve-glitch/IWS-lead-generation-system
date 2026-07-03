import streamlit as st
import asyncio
from core.api_client import login, get_me, get_users, get_sources, APIError, APIConnectionError, APIAuthError
from core.auth import save_token_cookie, controller, COOKIE_NAME
from core.state import state
from core.styles import inject_global_styles

st.set_page_config(page_title="Login — Lead Management", page_icon="", layout="wide")

inject_global_styles()


# ── Check if already logged in (session_state OR cookie) ──
if state.token:
    user_info = state.user or {}
    st.success(f"Already logged in as **{user_info.get('name', '')}** ({user_info.get('role', '')})")
    st.page_link("pages/1_Dashboard.py", label="Go to Dashboard", icon="📊")
    st.stop()

# Try cookie recovery
saved_token = controller.get(COOKIE_NAME)
if saved_token:
    try:
        user = get_me(saved_token)
        state.token = saved_token
        state.user = user
        # UPDATE: Point to the new Dashboard route
        st.switch_page("pages/1_Dashboard.py")
    except Exception:
        controller.remove(COOKIE_NAME)

# ── Login Card ──
st.markdown("<br>", unsafe_allow_html=True)

_, center_col, _ = st.columns([1, 1.5, 1])

with center_col:
    st.markdown("""
    <div style="
        border: 1px solid rgba(54,57,62,0.3);
        border-radius: 10px;
        padding: 40px 36px 30px 36px;
        background: white;
        margin-top: 40px;
    ">
        <h1 style="font-weight: 800; margin-bottom: 4px; font-size: 1.8rem;">Lead Management System</h1>
        <p style="color: #888; font-size: 0.95rem; margin-bottom: 24px;">Sign in to your account</p>
    </div>
    """, unsafe_allow_html=True)

    with st.form("login_form"):
        email = st.text_input("Email", placeholder="admin@example.com")
        password = st.text_input("Password", type="password", placeholder="Enter your password")
        submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")

    if submitted:
        if not email or not password:
            st.error("Please enter both email and password.")
        else:
            try:
                result = login(email, password)
                token = result["access_token"]
                refresh_token = result.get("refresh_token")
                user = get_me(token)

                state.token = token
                state.user = user
                if refresh_token:
                    state.refresh_token = refresh_token
                
                # Save both to cookie as a JSON string
                import json
                save_token_cookie(json.dumps({"access": token, "refresh": refresh_token}))

                # Eager Loading: Prime the cache for frequently accessed data
                try:
                    get_users(token)
                    get_sources(token)
                except Exception:
                    pass

                st.switch_page("pages/1_Dashboard.py")

            except APIAuthError:
                st.error("Invalid email or password.")
            except APIConnectionError as e:
                st.error(f"Backend offline: {e}")
            except APIError as e:
                st.error(f"Login failed: {e}")

    # ── Quick login hints ──
    st.markdown("---")
    st.caption("Demo Credentials")
    st.markdown("""
    | Role | Email | Password |
    |------|-------|----------|
    | Admin | `admin@example.com` | `admin123` |
    | Manager | `priya@iwsfinserve.com` | `manager123` |
    | Sales Rep | `rahul@iwsfinserve.com` | `rahul123` |
    """)
