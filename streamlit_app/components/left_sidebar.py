# streamlit_app/components/left_sidebar.py

import streamlit as st
from api.history.history_api import (
    get_all_history,
    update_history_title,
)


def render_left_sidebar():
    st.title("🧠 RAGNOZA")
    st.caption("AI Legal Assistant")
    st.divider()

    search_query = st.text_input(
        "Search",
        placeholder="Cari riwayat..."
    )

    st.divider()

    st.markdown("#### 📋 Riwayat Generate")

    # =====================================
    # Refresh History
    # =====================================
    if st.button(
        "🔄 Refresh",
        use_container_width=True,
        key="btn_refresh_history",
    ):
        st.session_state.pop("_db_history_cache", None)
        st.rerun()

    force_refresh = st.session_state.pop(
        "_force_refresh_history",
        False,
    )

    if "_db_history_cache" not in st.session_state or force_refresh:
        resp = get_all_history()
        st.session_state["_db_history_cache"] = (
            resp.get("data", [])
            if resp
            else []
        )

    db_histories = st.session_state.get(
        "_db_history_cache",
        [],
    )

    # =====================================
    # Filter
    # =====================================
    filtered_db = [
        h for h in db_histories
        if search_query.lower()
        in (h.get("search_query") or "").lower()
        or search_query.lower()
        in (h.get("repaired_text") or "").lower()
        or search_query.lower()
        in (h.get("session_title") or "").lower()
    ]

    if not filtered_db:
        st.caption("Belum ada riwayat generate.")

    # =====================================
    # List History
    # =====================================
    for h in filtered_db:

        score = h.get("compliance_score", "-")
        status = h.get("decision_status", "-")
        kb = h.get("knowledge_base", "-")
        created = str(h.get("created_at", ""))[:16]

        ragas_st = h.get("ragas_status", "skipped")

        ragas_icon = {
            "success": "📊",
            "error": "⚠️",
            "skipped": "⬜",
        }.get(ragas_st, "⬜")

        title = (
            h.get("session_title")
            or h.get("search_query")
            or "Session Tanpa Judul"
        )

        col1, col2 = st.columns([8, 1])

        # ==========================
        # Open Detail
        # ==========================
        with col1:
            if st.button(
                f"{ragas_icon} [{score}] {title[:40]}",
                key=f"db_hist_{h['id']}",
                use_container_width=True,
            ):
                st.session_state["selected_history_id"] = h["id"]
                st.session_state["selected_history"] = h
                st.session_state.current_session_id = None
                st.rerun()

        # ==========================
        # Edit Button
        # ==========================
        with col2:
            if st.button(
                "✏️",
                key=f"edit_title_{h['id']}",
                use_container_width=True,
            ):
                st.session_state["editing_history_id"] = h["id"]

        st.caption(
            f"🗂 {kb} · {created} · {status}"
        )

        # ==========================
        # Edit Title Form
        # ==========================
        if (
            st.session_state.get("editing_history_id")
            == h["id"]
        ):

            new_title = st.text_input(
                "Judul Session",
                value=title,
                key=f"title_input_{h['id']}",
            )

            save_col, cancel_col = st.columns(2)

            with save_col:
                if st.button(
                    "💾 Simpan",
                    key=f"save_title_{h['id']}",
                    use_container_width=True,
                ):

                    success = update_history_title(
                        history_id=h["id"],
                        session_title=new_title.strip(),
                    )

                    if success:
                        st.success(
                            "Judul berhasil diperbarui"
                        )

                        st.session_state.pop(
                            "_db_history_cache",
                            None,
                        )

                        st.session_state.pop(
                            "editing_history_id",
                            None,
                        )

                        st.rerun()

                    else:
                        st.error(
                            "Gagal memperbarui judul"
                        )

            with cancel_col:
                if st.button(
                    "❌ Batal",
                    key=f"cancel_title_{h['id']}",
                    use_container_width=True,
                ):
                    st.session_state.pop(
                        "editing_history_id",
                        None,
                    )
                    st.rerun()

        st.markdown("---")

    # =====================================
    # Summary Metrics
    # =====================================
    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.metric(
            "Total Session",
            len(db_histories),
        )

    with col2:
        st.metric(
            "Dengan RAGAS",
            len(
                [
                    h
                    for h in db_histories
                    if h.get("ragas_status") == "success"
                ]
            ),
        )