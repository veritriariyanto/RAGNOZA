# streamlit_app/app.py

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

    selected = st.session_state.get("selected_history")
    if selected:
        # Tampilkan info sumber dari history yang dipilih
        kb      = selected.get("knowledge_base", "-")
        score   = selected.get("compliance_score", "-")
        status  = selected.get("decision_status", "-")
        created = str(selected.get("created_at", ""))[:16]

        st.metric("Knowledge Base", kb)
        st.metric("Compliance Score", score)
        st.metric("Status", status)
        st.caption(f"🕐 {created}")

        raw_context = selected.get("raw_context") or selected.get("context") or ""
        if raw_context:
            st.divider()
            st.caption("📄 Cuplikan Context:")
            st.info(raw_context[:300] + ("..." if len(raw_context) > 300 else ""))
    else:
        # Placeholder default
        st.write("### Pasal 1")
        st.success("Similarity Score: 0.94")
        st.write("### Isi Teks")
        st.info("Negara Indonesia ialah Negara Kesatuan yang berbentuk Republik.")
        st.write("### Metadata")
        st.write("Pasal: 1")
        st.write("Bab: BAB I")
        st.write("Sumber: UUD 1945")
        st.button("📄 Lihat Dokumen Asli", use_container_width=True)