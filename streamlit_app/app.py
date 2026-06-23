# streamlit_app/app.py

import streamlit as st

from components.left_sidebar import render_left_sidebar
from components.top_tabs import render_top_tabs
from components.audio_controls import render_audio_controls
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
# MAIN LAYOUT (Halaman Normal - Memenuhi Layar)
# =========================================
with st.sidebar:
    render_left_sidebar()

# 💡 Perbaikan: Langsung render tanpa dibungkus left_col / center_col
tab1, tab2 = render_top_tabs()

with tab1:
    render_knowledgebase_tab()

with tab2:
    render_audio_controls()