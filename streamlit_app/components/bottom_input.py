# streamlit_app/components/bottom_input.py

import streamlit as st

from utils.session import get_current_session, pop_pending_audio_text
from api.prompting.rag_api import ask_rag


def render_bottom_input():

    current_session = get_current_session()

    # =========================================
    # JIKA BELUM ADA SESSION
    # =========================================
    if current_session is None:
        st.info("Buat chat baru terlebih dahulu.")
        return

    # =========================================
    # CEK PENDING AUDIO TEXT
    # Jika ada transkripsi audio yang baru selesai, pre-fill ke input
    # =========================================
    pending = pop_pending_audio_text()

    # =========================================
    # CHAT INPUT
    # =========================================
    prompt = st.chat_input(
        "Ketik pertanyaan Anda...",
        key="chat_input",
    )

    # Jika tidak ada input manual tapi ada pending audio, gunakan teks audio
    if not prompt and pending:
        prompt = pending

    # =========================================
    # JIKA ADA INPUT (manual ATAU dari audio)
    # =========================================
    if prompt:

        # --- User message ---
        current_session["messages"].append({
            "role": "user",
            "content": prompt,
        })

        # =====================================
        # CALL FASTAPI
        # =====================================
        with st.spinner("RAGNOZA sedang berpikir..."):
            response = ask_rag(prompt, session_id=current_session["id"])

        # =====================================
        # HANDLE ERROR
        # =====================================
        if response.get("error"):
            st.error(f"⚠️ {response['error']}")
            # Tetap simpan pesan error sebagai balasan agar konteks terjaga
            current_session["messages"].append({
                "role": "assistant",
                "content": f"_(Error: {response['error']})_",
            })
        else:
            ai_answer = response.get("answer", "Tidak ada jawaban.")

            # Simpan sumber ke session agar right panel bisa membacanya
            current_session["last_sources"] = response.get("sources", [])

            # --- Assistant message ---
            current_session["messages"].append({
                "role": "assistant",
                "content": ai_answer,
            })

        st.rerun()