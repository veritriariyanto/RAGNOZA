import streamlit as st

def init_session():
    if "sessions" not in st.session_state:
        st.session_state.sessions = {
            "Session 1": []
        }

    if "current_session" not in st.session_state:
            st.session_state.current_session = "Session 1"

def get_current_messages():
    return st.session_state.sessions[
          st.session_state.current_session
    ]

def create_new_session():
     session_count = len(st.session_state.sessions) + 1
     new_name = f"Session {session_count}"

     st.session_state.sessions[new_name] = []

     st.session_state.current_session = new_name
        

    
            

            