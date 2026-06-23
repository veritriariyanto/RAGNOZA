# components/top_tabs.py

import streamlit as st

def render_top_tabs():
    tab1, tab2 = st.tabs([
        "📚 KNOWLEDGEBASE",
        "⚡ GENERATE",
    ])

    return tab1, tab2

