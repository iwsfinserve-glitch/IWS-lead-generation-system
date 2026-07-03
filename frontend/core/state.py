import streamlit as st
from typing import Optional, Dict, Any

class SessionState:
    """Typed wrapper for streamlit session state variables."""
    
    @property
    def token(self) -> Optional[str]:
        return st.session_state.get("token")
        
    @token.setter
    def token(self, value: Optional[str]):
        st.session_state["token"] = value

    @property
    def refresh_token(self) -> Optional[str]:
        return st.session_state.get("refresh_token")
        
    @refresh_token.setter
    def refresh_token(self, value: Optional[str]):
        st.session_state["refresh_token"] = value
        
    @property
    def user(self) -> Optional[Dict[str, Any]]:
        return st.session_state.get("user")
        
    @user.setter
    def user(self, value: Optional[Dict[str, Any]]):
        st.session_state["user"] = value
        
    def clear(self):
        """Clears all authentication-related state variables."""
        for key in list(st.session_state.keys()):
            del st.session_state[key]

# Singleton instance to be used across the app
state = SessionState()
