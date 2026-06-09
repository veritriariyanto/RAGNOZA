import streamlit as st

from components.left_sidebar import render_left_sidebar
from components.top_tabs import render_top_tabs
from components.audio_controls import render_audio_controls
from components.evaluation_tab import render_evaluation_tab
from components.knowledgebase_tab import render_knowledgebase_tab
from components.history_detail import render_history_detail   # ← BARU

from utils.session import init_session_state


# =========================================
# PAGE CONFIG
# =========================================
st.set_page_config(
    page_title="RAGNOZA",
    page_icon="🧠",
    layout="wide"
)

# =========================================
# INIT SESSION
# =========================================
init_session_state()

# =========================================
# TRIGGER REDIRECT (KUNCI PENYELESAIAN)
# =========================================
# Cek apakah ada trigger dari audio_controls untuk pindah halaman
if st.session_state.get("trigger_redirect_hasil"):
    # Hapus flag agar tidak terjadi looping redirect nantinya
    st.session_state["trigger_redirect_hasil"] = False
    
    # Jalankan pengalihan halaman di level root
    st.switch_page("pages/1_Hasil_Generate.py")


# =========================================
# MAIN LAYOUT
# =========================================
left_col, center_col, right_col = st.columns([1.2, 3.8, 1.4])

# =========================================
# LEFT SIDEBAR
# =========================================
with st.sidebar:
    render_left_sidebar()

# =========================================
# CENTER CHAT AREA
# =========================================
with center_col:

    tab1, tab2, tab3 = render_top_tabs()

    # =====================================
    # TAB KNOWLEDGEBASE
    # =====================================
    with tab1:
        render_knowledgebase_tab()

    # =====================================
    # TAB GENERATE
    # =====================================
    with tab2:

        # ── ROUTING: jika ada history yang dipilih, tampilkan detailnya ──────
        # Ketika user klik item di sidebar "Riwayat Generate",
        # left_sidebar.py menyimpan data ke selected_history.
        # Di sini kita cek keberadaannya dan route ke komponen yang sesuai.
        if st.session_state.get("selected_history"):
            render_history_detail()
        else:
            # Mode normal — form audio + generate baru
            render_audio_controls()


    # =====================================
    # TAB EVALUASI
    # =====================================
    with tab3:
        render_evaluation_tab()

# =========================================
# RIGHT PANEL
# =========================================
with right_col:

    st.subheader("📄 Detail Sumber")

    st.divider()

    st.write("### Pasal 1")

    st.success("Similarity Score: 0.94")

    st.write("### Isi Teks")

    st.info("""
    Negara Indonesia ialah Negara Kesatuan
    yang berbentuk Republik.
    """)

    st.write("### Metadata")

    st.write("Pasal: 1")
    st.write("Bab: BAB I")
    st.write("Sumber: UUD 1945")

    st.button(
        "📄 Lihat Dokumen Asli",
        use_container_width=True
    )