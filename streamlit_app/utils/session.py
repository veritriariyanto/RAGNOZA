import streamlit as st
import uuid
from datetime import datetime

# =========================================
# INIT SESSION STATE
# =========================================
def init_session_state():

    defaults = {
        "chat_sessions": [],
        "current_session_id": None,
    }

    for key, value in defaults.items():

        if key not in st.session_state:
            st.session_state[key] = value

# =========================================
# CREATE NEW CHAT SESSION
# =========================================
def create_new_session ():

    session_id = str(uuid.uuid4())[:8]

    new_session = {
        "id": session_id,
        "title": f"New Chat {datetime.now().strftime('%H:%M')}",
        "messages": [],
        "created_at": datetime.now()
    }

    st.session_state.chat_sessions.insert(
        0, 
        new_session
    )

    st.session_state.current_session_id = session_id

# =========================================
# GET CURRENT SESSION
# =========================================
def get_current_session():
    current_id = st.session_state.current_session_id
    for session in st.session_state.chat_sessions:
        if session["id"] == current_id:
            return session
        
    return None
    
# =========================================
# DELETE SESSION
# =========================================
def delete_session(session_id):
    st.session_state.chat_sessions = [
        s for s in st.session_state.chat_sessions 
        if s["id"] != session_id
    ]

    if st.session_state.current_session_id == session_id:
        st.session_satte.current_session_id = None