import streamlit as st

def render_sidebar():
    st.sidebar.markdown(
        """
        <style>
        /* Hide the default Streamlit sidebar navigation */
        [data-testid="stSidebarNav"] {
            display: none;
        }
        
        /* Custom Sidebar Styles */
        .sidebar-title {
            font-size: 24px;
            font-weight: 800;
            color: #31333F;
            margin-bottom: 40px;
            margin-top: 10px;
            line-height: 1.3;
        }
        
        .custom-nav-btn {
            display: flex;
            align-items: center;
            padding: 14px 18px;
            margin-bottom: 12px;
            background-color: transparent;
            color: #31333F;
            text-decoration: none;
            border-radius: 8px;
            font-size: 18px;
            font-weight: 500;
            transition: all 0.2s;
        }
        
        .custom-nav-btn:hover {
            background-color: rgba(151, 166, 195, 0.15);
            color: #2196F3;
            text-decoration: none;
        }
        
        .custom-nav-btn i {
            margin-right: 18px;
            font-size: 22px; /* Increased icon size */
            width: 25px;
            text-align: center;
        }
        </style>
        
        <div class="sidebar-title">
            <h1 style='font-weight:bold; font-size: 1.9rem'>Lead Management<br>System</h1>
        </div>

        <hr>
        
        <a href="/" target="_self" class="custom-nav-btn">
            <i class="fa-solid fa-table-columns"></i> Dashboard
        </a>
        <a href="./pages/1_Appointments.py" target="_self" class="custom-nav-btn">
            <i class="fa-regular fa-calendar-check"></i> Appointments
        </a>
        """,
        unsafe_allow_html=True
    )
