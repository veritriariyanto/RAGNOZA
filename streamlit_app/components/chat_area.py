# streamlit_app/components/chat_area.py

import streamlit as st
from datetime import datetime
from utils.session import get_current_session


def _render_message(role: str, content: str, idx: int):
    """Render satu bubble pesan dengan avatar dan styling."""

    is_user = role == "user"
    avatar = "🧑" if is_user else "🧠"

    with st.chat_message(role, avatar=avatar):
        st.markdown(content)


def render_chat_area():

    current_session = get_current_session()

    # =========================================
    # HEADER
    # =========================================
    col1, col2 = st.columns([5, 1])

    with col1:
        st.subheader("🧠 Chat dengan AI RAGNOZA Assistant")
        st.caption("Jawaban dihasilkan berdasarkan knowledge base yang Anda upload.")

    with col2:
        if st.button("🗑️ Clear Chat", use_container_width=True):
            if current_session:
                current_session["messages"] = []
                current_session["last_sources"] = []
                st.rerun()

    st.divider()

    # =========================================
    # EMPTY STATE
    # =========================================
    if current_session is None:
        st.info("Buat chat baru terlebih dahulu.")
        return

    messages = current_session.get("messages", [])

    if not messages:
        # Welcome state
        st.markdown(
            """
            <div style='text-align:center; padding: 3rem 1rem; opacity: 0.5;'>
                <div style='font-size: 3rem;'>🧠</div>
                <p style='font-size: 1.1rem; margin-top: 0.5rem;'>
                    Tanyakan sesuatu tentang knowledge base Anda...
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # =========================================
    # RENDER SEMUA PESAN
    # =========================================
    for idx, message in enumerate(messages):
        _render_message(
            role=message["role"],
            content=message["content"],
            idx=idx,
        )