import streamlit as st

from components.left_sidebar import render_left_sidebar
from components.top_tabs import render_top_tabs
from components.bottom_input import render_bottom_input
from components.audio_controls import render_audio_controls
from components.evaluation_tab import render_evaluation_tab
from components.knowledgebase_tab import render_knowledgebase_tab

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
left_col, center_col, right_col = st.columns(
    [1.2, 3.8, 1.4]
)

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

        render_audio_controls()

        render_bottom_input()

    # =====================================
    # TAB EVALUASI
    # =====================================
    with tab3:
        render_evaluation_tab()