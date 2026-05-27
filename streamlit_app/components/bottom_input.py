import streamlit as st

from utils.session import get_current_session
from streamlit_app.api.prompting.rag_api import ask_rag

def render_bottom_input():

    current_session = get_current_session()

    # =========================================
    # JIKA BELUM ADA SESSION
    # =========================================
    if current_session is None:
        st.info ("Buat chat baru terlebih dahulu.")

        return
    # =========================================
    # CHAT INPUT
    # =========================================
    prompt = st.chat_input (
        "Ketika pertanyaan Anda..."
    )

    # =========================================
    # JIKA USER INPUT
    # =========================================
    if prompt:

        #User message
        user_message = {
            "role": "user",
            "content": prompt
        }

        current_session["messages"].append(user_message)

    # =====================================
    # CALL FASTAPI
    # =====================================  
    response = ask_rag(prompt)

    ai_response = response.get(
        "answer", 
        "Tidak ada jawaban."
    ) 

    # =====================================
    # ASSISTANT MESSAGE
    # =====================================
    assistant_message = {
        "role": "assistant",
        "content": ai_response
    }

    current_session["messages"].append(assistant_message)

    st.rerun()