# streamlit_app/components/left_sidebar.py

import streamlit as st
from components.audio_controls import _inject_styles
from api.history.history_api import (
    get_all_history,
    get_history_detail,
    update_history_title,
)


def render_left_sidebar():
    _inject_styles()
    st.markdown(
    """
    <div class="ac-header">🧠 RAGNOZA</div>
    <div class="ac-subheader">AI Legal Assistant</div>
    """,
    unsafe_allow_html=True,
)
    st.divider()

    st.markdown('<div class="ac-label">Cari Riwayat</div>', unsafe_allow_html=True)
    search_query = st.text_input("Search", placeholder="Cari riwayat...", label_visibility="collapsed")

    st.divider()

    st.markdown('<div class="result-header">📋 Riwayat Generate</div>', unsafe_allow_html=True)

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

    force_refresh = st.session_state.get(
        "_force_refresh_history",
        False,
    )

    if "_db_history_cache" not in st.session_state or force_refresh:
        st.session_state.pop("_force_refresh_history", None)
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
        st.markdown(
            '<div style="font-family:\'DM Sans\',sans-serif;font-size:0.78rem;'
            'color:#6B6460;text-align:center;padding:12px 0;">Belum ada riwayat generate.</div>',
            unsafe_allow_html=True,
        )

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

        col1, col2 = st.columns([7, 1.5], vertical_alignment="center")

        # ==========================
        # Open Detail
        # ==========================
        with col1:
            if st.button(
                f"{ragas_icon} [{score}] {title[:40]}",
                key=f"db_hist_{h['id']}",
                use_container_width=True,
            ):
                # List endpoint (/history) tidak mengembalikan ragas_metrics,
                # generate_material, retrieved_context — harus fetch detail.
                with st.spinner("Memuat detail riwayat..."):
                    detail_resp = get_history_detail(h["id"])
                    # get_history_detail mengembalikan full response JSON:
                    # {"status": "success", "data": {...}}
                    # Ambil field "data" jika ada, fallback ke dict kosong
                    detail = detail_resp.get("data", {}) if detail_resp else {}

                print(f"[DEBUG SIDEBAR] detail ragas_status = {detail.get('ragas_status')}")
                print(f"[DEBUG SIDEBAR] detail ragas_metrics = {detail.get('ragas_metrics')}")

                st.session_state["selected_history_id"] = h["id"]
                st.session_state["selected_history"] = detail if detail else h
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

        st.markdown(
            f'<div style="font-family:\'DM Sans\',sans-serif;font-size:0.72rem;'
            f'color:#6B6460;padding:2px 0 6px 2px;letter-spacing:0.02em;">'
            f'🗂 {kb} &nbsp;·&nbsp; {created} &nbsp;·&nbsp; {status}</div>',
            unsafe_allow_html=True,
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

        st.markdown('<div class="ac-divider"></div>', unsafe_allow_html=True)

    # =====================================
    # Summary Metrics
    # =====================================
    st.divider()
    st.markdown('<div class="section-label">📈 Ringkasan</div>', unsafe_allow_html=True)

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