import streamlit as st
from utils.session import create_new_session
from api.history.history_api import get_all_history

def render_left_sidebar():
    with st.sidebar:
        st.title("🧠 RAGNOZA")
        st.caption("AI Assistant")
        
        # Tombol New Chat
        if st.button("➕ New Chat", use_container_width=True, type="primary"):
            # 1. Jalankan fungsi create session untuk membersihkan database/state
            create_new_session()
            
            # 2. Reset ID session aktif ke None
            st.session_state.current_session_id = None
            
            # 3. Alihkan navigasi kembali ke halaman utama (app.py)
            st.switch_page("app.py")

        # Pencarian riwayat
        search = st.text_input("Search", placeholder="🔍 Cari...", label_visibility="collapsed")
        st.divider()

        # Ambil data sesi dari API (Postgres)
        res = get_all_history()
        sessions = res.get("data", []) if res.get("status") == "success" else []
        st.session_state.chat_sessions = sessions

        # Filter berdasarkan pencarian
        filtered = [s for s in sessions if search.lower() in s.get('title', '').lower()]

        st.markdown("### 🕒 Riwayat Chat")
        if not filtered:
            st.info("Belum ada sesi chat.")
        else:
            for sess in filtered:
                is_active = st.session_state.get("current_session_id") == sess["id"]
                title = sess.get('title', 'Untitled')
                score = sess.get('compliance_score')
                display = f"{'📍 ' if is_active else '💬 '}{title}"
                if score:
                    display += f" ({score})"

                # Tombol sesi (tanpa tombol hapus)
                btn_type = "primary" if is_active else "secondary"
                if st.button(display, key=f"chat_{sess['id']}", use_container_width=True, type=btn_type):
                    st.session_state.current_session_id = sess["id"]
                    st.switch_page("pages/1_Hasil_Generate.py")

        # Footer total sesi
        st.divider()
        c1, c2 = st.columns([2, 1])
        c1.caption("Total Sesi:")
        c2.markdown(f"**{len(sessions)}**")