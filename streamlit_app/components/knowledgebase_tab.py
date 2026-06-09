import streamlit as st
import pandas as pd

from api.knowledge.knowledge_api import (
get_knowledgebase_stats,
get_knowledgebase_list
)

def render_knowledgebase_tab():


    st.subheader("📚 Knowledge Base")

    st.markdown(
    '<div class="white-caption">Monitoring collection dan vector database Qdrant.</div>',
    unsafe_allow_html=True
    )

    st.divider()

# =====================================
# GET KNOWLEDGE BASE LIST
# =====================================

    kb_list = get_knowledgebase_list()

    if not kb_list:
        st.warning("Belum ada knowledge base.")
        return

# =====================================
# SELECT KNOWLEDGE BASE
# =====================================

    selected_kb = st.selectbox(
        "Pilih Knowledge Base",
        kb_list
    )

# =====================================
# GET STATS
# =====================================

    data = get_knowledgebase_stats(selected_kb)

# =====================================
# STATISTICS
# =====================================

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Parent Count",
            data.get("parent_count", 0)
        )

    with col2:
        st.metric(
            "Child Count",
            data.get("child_count", 0)
        )

    with col3:
        st.metric(
            "Status",
            data.get("status", "N/A")
        )

    st.divider()

# =====================================
# COLLECTION TABLE
# =====================================

    st.markdown("### 📄 Collection Details")

    df = pd.DataFrame([data])

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )
