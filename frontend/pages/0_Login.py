import streamlit as st
from api_client import login, get_me

st.set_page_config(page_title="Login — Lead Management", page_icon="", layout="wide")

# ── CSS: Same dotted background + centered form ──
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

# If already logged in, show a message and redirect
if "token" in st.session_state and st.session_state.token:
    st.success(f"Already logged in as **{st.session_state.user.get('name', '')}** ({st.session_state.user.get('role', '')})")
    st.page_link("app.py", label="Go to Dashboard", icon="📊")
    st.stop()

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
                user = get_me(token)

                st.session_state.token = token
                st.session_state.user = user

                st.success(f"Welcome, **{user['name']}**!")
                st.switch_page("app.py")

            except Exception as e:
                error_msg = str(e)
                if "401" in error_msg:
                    st.error("Invalid email or password.")
                elif "Connection" in error_msg:
                    st.error("Cannot connect to backend server. Make sure it's running on port 8000.")
                else:
                    st.error(f"Login failed: {error_msg}")

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
