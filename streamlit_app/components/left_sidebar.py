import streamlit as st
from utils.session import (create_new_session, delete_session)

def render_left_sidebar():

    st.title("🧠 RAGNOZA")

    st.caption("AI RAGNOZA Assistant")

    st.divider()

    # =========================================
    # SEARCH
    # =========================================
    search_query = st.text_input (
        "Search",
        placeholder="Cari riwayat..."
    )

    # =========================================
    # NEW CHAT
    # =========================================
    if st.button(
        "➕ New Chat",
        use_container_width=True
    ):

        create_new_session()

        st.rerun()

    st.divider()

    # =========================================
    # FILTER SESSION
    # =========================================
    filtered_sessions = []
    for session in st.session_state.chat_sessions:
        if (
            search_query.lower()
            in session['title'].lower()
        ):
            filtered_sessions.append(session)

    # =========================================
    # SESSION LIST
    # =========================================
    if not filtered_sessions:
        st.info("Belum ada sesi chat.")

    for session in filtered_sessions:
        col1, col2 = st.columns([5, 1])

        with col1:
            if st.button (
                f"💬 {session['title']}",
                key=session["id"],
                use_container_width=True
            ):
                st.session_state.current_session_id = session["id"]

            st.rerun()

        with col2:
            if st.button(
                "🗑️",
                key=f"delete_{session['id']}"
            ):
                delete_session(session["id"])

                st.rerun()

    st.divider()

    st.metric(
        "Total Chat Sessions",
        len(st.session_state.chat_sessions)
    )