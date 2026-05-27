import streamlit as st

def render_top_tabs():
    tab1, tab2, tab3 = st.tabs([
        "📚 KNOWLEDGEBASE",
        "⚡ GENERATE",
        "📊 EVALUASI"
    ])

    return tab1, tab2, tab3

