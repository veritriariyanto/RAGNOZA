import streamlit as st
from utils.session import get_current_session

def render_chat_area():

    current_session = get_current_session()

    # =========================================
    # HEADER
    # =========================================

    col1, col2 = st.columns([5, 1])

    with col1:
        st.subheader("🧠 Chat dengan AI RAGNOZA Assistant")

        st.caption(
            "Jawaban dihasilkan berdasarkan knowledge base yang Anda upload."
        )

    with col2:
            
        if st.button (
            "🗑️ Clear Chat",
            use_container_width=True
        ):

            if current_session:
                current_session["messages"] = []

                st.rerun()

        st.divider()

    # =========================================
    # EMPTY STATE
    # =========================================
    if current_session is None:
        st.info ("Buat chat baru terlebih dahulu.")

        return

    # =========================================
    # RENDER CHAT
    # =========================================
    for message in current_session["messages"]:

        with st.chat_message(message["role"]):

            st.write(message["content"])