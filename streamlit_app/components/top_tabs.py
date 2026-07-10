# components/top_tabs.py

import streamlit as st

def render_top_tabs():
    tab1, tab2, tab3 = st.tabs([
        "📚 KNOWLEDGEBASE",
        "⚡ GENERATE",
        "📁 EVALUASI DATASET"
    ])

    return tab1, tab2, tab3