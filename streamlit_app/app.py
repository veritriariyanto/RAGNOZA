import streamlit as st

from components.left_sidebar import render_left_sidebar
from components.top_tabs import render_top_tabs
from components.audio_controls import render_audio_controls
from components.evaluation_tab import render_evaluation_tab
from components.knowledgebase_tab import render_knowledgebase_tab
from components.history_detail import render_history_detail_page  # ← ganti import

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
# ROUTING — History Detail Page
# Jika user memilih riwayat dari sidebar,
# render FULL PAGE history (tanpa kolom/tab lain).
# =========================================
if st.session_state.get("selected_history"):
    render_history_detail_page()
    st.stop()  # ← hentikan eksekusi, tidak render layout normal di bawah

# =========================================
# MAIN LAYOUT (halaman normal)
# =========================================
with st.sidebar:
    render_left_sidebar()

left_col, center_col, right_col = st.columns([1.2, 3.8, 1.4])

with center_col:
    tab1, tab2, tab3 = render_top_tabs()

    with tab1:
        render_knowledgebase_tab()

    with tab2:
        render_audio_controls()

    with tab3:
        render_evaluation_tab()