# components/left_sidebar.py

import streamlit as st
from utils.session import create_new_session
# Import fungsi API client yang mengarah ke Postgres
from api.history.history_api import get_all_history, delete_history

def render_left_sidebar():

    st.title("🧠 RAGNOZA")
    st.caption("AI RAGNOZA Assistant")
    st.divider()

    # =========================================
    # SEARCH
    # =========================================
    search_query = st.text_input(
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
        # Reset session yang aktif ke None agar kembali ke halaman kosong
        st.session_state.current_session_id = None
        st.rerun()

    st.divider()

    # =========================================
    # FETCH DATA FROM POSTGRES (Sinkronisasi API)
    # =========================================
    # Kita ambil data riwayat langsung dari DB untuk menggantikan state lokal
    api_res = get_all_history()
    if api_res.get("status") == "success":
        st.session_state.chat_sessions = api_res.get("data", [])
    else:
        st.session_state.chat_sessions = []

    # =========================================
    # FILTER SESSION
    # =========================================
    filtered_sessions = []
    for session in st.session_state.chat_sessions:
        # Cek berdasarkan properti 'title' dari tabel LegalMaterialHistory
        if search_query.lower() in session.get('title', '').lower():
            filtered_sessions.append(session)

    # =========================================
    # SESSION LIST
    # =========================================
    if not filtered_sessions:
        st.info("Belum ada sesi chat.")

    for session in filtered_sessions:
        col1, col2 = st.columns([5, 1])

        with col1:
            # Tampilkan Judul dan Compliance Score (jika ada)
            score_tag = f" ({session['compliance_score']})" if session.get('compliance_score') else ""
            button_label = f"💬 {session.get('title', 'Untitled')}{score_tag}"
            
            if st.button(
                button_label,
                key=f"session_{session['id']}", 
                use_container_width=True
            ):
                # 1. Amankan ID yang dipilih ke session_state global
                st.session_state.current_session_id = session["id"]
                
                # 2. PENGALIHAN HALAMAN: Paksa pindah ke halaman 1_Hasil_Generate.py
                # Masukkan jalur path file-nya dihitung dari root project (sejajar app.py)
                st.switch_page("pages/1_Hasil_Generate.py")

        with col2:
            if st.button(
                "🗑️",
                key=f"delete_{session['id']}"
            ):
                # 1. Hapus data secara permanen di Postgres via API
                delete_res = delete_history(session["id"])
                
                if delete_res.get("status") == "success":
                    st.toast(f"Berhasil menghapus riwayat!")
                    
                    # 2. Jika sesi yang dihapus kebetulan sedang dibuka, reset view tengah ke kosong
                    if st.session_state.get("current_session_id") == session["id"]:
                        st.session_state.current_session_id = None
                        
                    st.rerun()
                else:
                    st.error("Gagal menghapus dari database.")

    st.divider()

    st.metric(
        "Total Chat Sessions",
        len(st.session_state.chat_sessions)
    )