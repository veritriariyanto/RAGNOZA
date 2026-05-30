# streamlit_app/utils/session.py

"""
streamlit_app/utils/session.py  (updated)
 
Perubahan:
- Tambah key untuk menyimpan hasil RAG pipeline (material + context + transcription)
- Tambah key untuk menyimpan hasil evaluasi RAGAS
- Keduanya dipakai bersama antara audio_controls (Generate tab) dan evaluation_tab
"""

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
        # Teks transkripsi audio yang menunggu dikirim ke chat input
        "pending_audio_text": "",
    # ── Hasil RAG pipeline terakhir ──────────────────────────────
        # Diisi oleh audio_controls setelah process-integrated berhasil.
        # Dibaca oleh evaluation_tab untuk auto-populate form.
        "last_rag_result": None,
        # Struktur last_rag_result:
        # {
        #   "question": str,          # repaired_text dari STT
        #   "context": str,           # combined context dari Qdrant
        #   "answer_text": str,       # material dalam format teks plain
        #   "generated_material": dict,
        #   "transcription_raw": str,
        #   "knowledge_base": str,
        #   "timestamp": str,
        # }
 
        # ── Hasil evaluasi RAGAS terakhir ────────────────────────────
        # Diisi oleh audio_controls setelah evaluasi selesai.
        # Dibaca oleh audio_controls (strip kecil) dan evaluation_tab (detail lengkap).
        "last_ragas_result": None,
        # Struktur last_ragas_result:
        # {
        #   "status": "success" | "error",
        #   "metrics": { faithfulness, answer_relevancy, context_precision,
        #                context_recall, overall_score },
        #   "error": str | None,
        #   "timestamp": str,
        # }
 
        # ── Flag loading state ───────────────────────────────────────
        # True saat evaluasi RAGAS sedang berjalan (untuk spinner di UI)
        "ragas_evaluating": False,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

# =========================================
# RAG RESULT HELPERS
# =========================================
def set_last_rag_result(
    question: str,
    context: str,
    answer_text: str,
    generated_material: dict | None,
    transcription_raw: str,
    knowledge_base: str, 
    sources_count: int = 0,
    has_context: bool = False,
    query_used: str = "",
):
    """Simpan hasil RAG pipeline ke session state."""
    st.session_state.last_rag_result = {
        "question": question,
        "context": context,
        "answer_text": answer_text,
        "generated_material": generated_material,
        "transcription_raw": transcription_raw,
        "knowledge_base": knowledge_base,
        "timestamp": datetime.now().isoformat(),
        "sources_count": sources_count,
        "has_context": has_context,
        "query_used": query_used,
        "timestamp": datetime.now().isoformat(),
    }

def get_last_rag_result() -> dict | None:
    """Ambil hasil RAG pipeline terakhir."""
    return st.session_state.get("last_rag_result")

def clear_last_rag_result():
    st.session_state.last_rag_result = None
    st.session_state.last_ragas_result = None

# =========================================
# RAGAS RESULT HELPERS
# =========================================  

def set_last_ragas_result(result: dict):
    """Simpan hasil evaluasi RAGAS ke session state."""
    if not isinstance(result, dict):
        st.session_state.last_ragas_result = {
            "status": "error",
            "error": f"Invalid result type: {type(result)}",
            "metrics": {},
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }
    else:
        st.session_state.last_ragas_result = {
            **result,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }
    st.session_state.ragas_evaluating = False

def get_last_ragas_result() -> dict | None:
    """Ambil hasil evaluasi RAGAS terakhir."""
    return st.session_state.get("last_ragas_result")

def set_ragas_evaluating(is_evaluating: bool):
    st.session_state.ragas_evaluating = is_evaluating

def is_ragas_evaluating() -> bool:
    return st.session_state.get("ragas_evaluating", False)
 

# =========================================
# CREATE NEW CHAT SESSION
# =========================================
def create_new_session():
    session_id = str(uuid.uuid4())[:8]

    new_session = {
        "id": session_id,
        "title": f"New Chat {datetime.now().strftime('%H:%M')}",
        "messages": [],
        "created_at": datetime.now(),
    }

    st.session_state.chat_sessions.insert(0, new_session)
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
def delete_session(session_id: str):
    st.session_state.chat_sessions = [
        s for s in st.session_state.chat_sessions
        if s["id"] != session_id
    ]

    # FIX: typo 'st.session_satte' → 'st.session_state'
    if st.session_state.current_session_id == session_id:
        st.session_state.current_session_id = None


# =========================================
# SET PENDING AUDIO TEXT
# Dipanggil dari audio_controls setelah transkripsi berhasil
# =========================================
def set_pending_audio_text(text: str):
    st.session_state.pending_audio_text = text


# =========================================
# POP PENDING AUDIO TEXT
# Dipanggil dari bottom_input untuk mengambil & membersihkan teks
# =========================================
def pop_pending_audio_text() -> str:
    text = st.session_state.get("pending_audio_text", "")
    st.session_state.pending_audio_text = ""
    return text