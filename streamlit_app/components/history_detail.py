# streamlit_app/components/history_detail.py

"""
Menampilkan detail riwayat generate yang dipilih dari sidebar.
Dibaca dari st.session_state["selected_history"] yang di-set oleh left_sidebar.

Struktur h (history object dari DB):
    id, search_query, repaired_text, knowledge_base,
    compliance_score, decision_status, created_at,
    ragas_status, ragas_metrics (dict),
    generated_material (dict), raw_context (str),
    sources_count, has_context, query_used
"""

import streamlit as st


# ── Helper: warna/emoji skor ─────────────────────────────────────────────────
def _score_emoji(score) -> str:
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "⬜"
    if s >= 0.8:
        return "🟢"
    if s >= 0.6:
        return "🟡"
    return "🔴"


def _badge(label: str, value, good_thresh=0.8, warn_thresh=0.6):
    """Render badge berwarna untuk skor 0–1."""
    try:
        v = float(value)
        if v >= good_thresh:
            bg, fg = "rgba(40,167,69,0.12)", "#1a7a35"
        elif v >= warn_thresh:
            bg, fg = "rgba(253,126,20,0.12)", "#b35c00"
        else:
            bg, fg = "rgba(220,53,69,0.12)", "#a01020"
        display = f"{v:.2f}"
    except (TypeError, ValueError):
        bg, fg, display = "rgba(150,150,150,0.12)", "#555", str(value) if value else "N/A"

    return (
        f'<span style="background:{bg};color:{fg};padding:2px 10px;'
        f'border-radius:5px;font-weight:600;font-size:13px;">'
        f'{_score_emoji(value) if value is not None else "⬜"} {label}: {display}</span>'
    )


# ── Render material (sama dengan audio_controls._render_material_result) ─────
def _render_material(material: dict, rag_info: dict):
    sources_count = rag_info.get("sources_count", 0)
    has_context   = rag_info.get("has_context", False)
    query_used    = rag_info.get("query_used", "-")

    col_a, col_b = st.columns(2)
    with col_a:
        st.caption(f"🔍 Query: *{query_used}*")
    with col_b:
        st.caption(f"📚 Sumber: {sources_count} chunk")

    if not has_context or not material:
        st.warning("⚠️ Tidak ditemukan referensi hukum yang relevan.")
        return

    # Summary
    summary = material.get("summary") or {}
    if summary:
        st.markdown(f"#### 📌 {summary.get('title', 'Ringkasan')}")
        if summary.get("overview"):
            st.write(summary["overview"])
        key_points = summary.get("key_points", [])
        if key_points:
            with st.expander("📋 Poin-Poin Penting", expanded=True):
                for point in key_points:
                    st.markdown(f"- {point}")
        if summary.get("conclusion"):
            st.info(f"💡 **Kesimpulan:** {summary['conclusion']}")

    # Legal Q&A
    legal_qa = material.get("legal_qa", [])
    if legal_qa:
        st.markdown("#### ❓ Legal Q&A")
        for qa in legal_qa:
            with st.expander(f"Q: {qa.get('question', '')}", expanded=False):
                st.write(qa.get("answer", "-"))

    # Risk Review
    risk = material.get("risk_review") or {}
    risk_status = risk.get("status", "-") or "-"
    if risk and risk_status not in ("-", "", "ERROR_SISTEM"):
        st.markdown("#### ⚠️ Risk Review")
        score = risk.get("score", 0) or 0
        col_s, col_sc = st.columns(2)
        with col_s:
            st.metric("Status", risk_status)
        with col_sc:
            st.metric("Skor Risiko", f"{score} / 100")
        st.progress(min(int(score), 100) / 100)
        if risk.get("analysis"):
            st.write(risk["analysis"])
        if risk.get("risks"):
            with st.expander("🔴 Risiko"):
                for r in risk["risks"]:
                    st.markdown(f"- {r}")
        if risk.get("mitigation_steps"):
            with st.expander("🛡️ Langkah Mitigasi"):
                for step in risk["mitigation_steps"]:
                    st.markdown(f"- {step}")
        if risk.get("recommendation"):
            st.success(f"✅ **Rekomendasi:** {risk['recommendation']}")

    # Clause Search
    clauses = material.get("clause_search", [])
    if clauses:
        with st.expander(f"📜 Pasal Terkait ({len(clauses)} ditemukan)"):
            for clause in clauses:
                st.markdown(
                    f"**{clause.get('article', '')}** — {clause.get('clause_topic', '')}"
                )
                if clause.get("excerpt"):
                    st.caption(clause["excerpt"])
                st.divider()

    # Timeline
    timeline = material.get("timeline_extraction", [])
    if timeline:
        with st.expander("🕐 Timeline Hukum"):
            for item in timeline:
                st.markdown(
                    f"- **{item.get('date_or_period', '')}** — "
                    f"{item.get('event', '')} "
                    f"*(Ref: {item.get('article_reference', '-')})*"
                )

    # Comparison
    comparisons = material.get("comparison", [])
    if comparisons:
        with st.expander("⚖️ Perbandingan Ketentuan"):
            for comp in comparisons:
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**{comp.get('aspect', '')}**")
                    st.write(comp.get("option_a") or comp.get("source_a", "-"))
                with col2:
                    st.write(comp.get("option_b") or comp.get("source_b", "-"))
                if comp.get("conclusion"):
                    st.caption(f"Kesimpulan: {comp['conclusion']}")
                st.divider()

    # Referensi UU
    referensi = material.get("referensi_uu", [])
    if referensi:
        with st.expander("📚 Referensi Undang-Undang"):
            for ref in referensi:
                st.markdown(
                    f"- **{ref.get('source_name', '')}** Pasal {ref.get('article', '')}"
                )


# ── Render RAGAS metrics ──────────────────────────────────────────────────────
def _render_ragas_section(h: dict):
    ragas_st = h.get("ragas_status", "skipped")
    metrics  = h.get("ragas_metrics") or {}

    st.markdown("### 📊 Evaluasi RAGAS")

    if ragas_st == "skipped":
        st.info("⬜ Evaluasi RAGAS tidak dijalankan untuk riwayat ini.")
        return

    if ragas_st == "error":
        st.error(f"⚠️ Evaluasi RAGAS gagal: {metrics.get('error', 'Unknown error')}")
        return

    # Status success — tampilkan metrik
    faith   = metrics.get("faithfulness")
    relev   = metrics.get("answer_relevancy")
    cp      = metrics.get("context_precision")
    cr      = metrics.get("context_recall")
    overall = metrics.get("overall_score")

    badges_html = " &nbsp; ".join([
        _badge("Faithfulness",      faith,   0.8, 0.6),
        _badge("Relevancy",         relev,   0.8, 0.6),
        _badge("Ctx Precision",     cp,      0.8, 0.6),
        _badge("Ctx Recall",        cr,      0.8, 0.6),
        _badge("Overall",           overall, 0.8, 0.6),
    ])
    st.markdown(badges_html, unsafe_allow_html=True)
    st.markdown("")

    # Detail metrik dengan st.metric
    m1, m2, m3, m4, m5 = st.columns(5)
    def _fmt(v): return f"{float(v):.2f}" if v is not None else "N/A"
    m1.metric("Faithfulness",    _fmt(faith))
    m2.metric("Answer Relevancy",_fmt(relev))
    m3.metric("Ctx Precision",   _fmt(cp))
    m4.metric("Ctx Recall",      _fmt(cr))
    m5.metric("Overall Score",   _fmt(overall))


# ── MAIN RENDER ───────────────────────────────────────────────────────────────
def render_history_detail():
    """
    Dipanggil dari app.py ketika st.session_state["selected_history"] terisi.
    Menampilkan semua detail history yang dipilih dari sidebar.
    """
    h = st.session_state.get("selected_history")

    if not h:
        # Placeholder saat belum ada history dipilih
        st.markdown(
            """
            <div style='text-align:center; padding:4rem 1rem; opacity:0.4;'>
                <div style='font-size:3rem;'>📋</div>
                <p style='font-size:1.1rem; margin-top:0.5rem;'>
                    Pilih riwayat dari sidebar untuk melihat detailnya.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # ── Header ────────────────────────────────────────────────────────────────
    col_title, col_back = st.columns([6, 1])
    with col_title:
        st.subheader("📋 Detail Riwayat Generate")
    with col_back:
        if st.button("✖ Tutup", use_container_width=True, key="btn_close_history"):
            st.session_state.pop("selected_history", None)
            st.session_state.pop("selected_history_id", None)
            st.rerun()

    st.divider()

    # ── Info ringkas ──────────────────────────────────────────────────────────
    created = str(h.get("created_at", ""))[:16]
    kb      = h.get("knowledge_base", "-")
    status  = h.get("decision_status", "-")
    score   = h.get("compliance_score", "-")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Compliance Score", score)
    c2.metric("Status",           status)
    c3.metric("Knowledge Base",   kb)
    c4.metric("Dibuat",           created)

    st.divider()

    # ── Query / Pertanyaan ────────────────────────────────────────────────────
    query = h.get("search_query") or h.get("repaired_text") or "-"
    st.markdown("### 🔍 Pertanyaan / Query")
    st.info(query)

    # Raw transcription (jika berbeda)
    raw = h.get("raw_transcribe")or ""
    if raw and raw != query:
        with st.expander("📝 Transkripsi Asli"):
            st.write(raw)

    st.divider()

    # ── Material Hasil Generate ───────────────────────────────────────────────
    st.markdown("### 📋 Hasil Analisis Hukum")

    material = h.get("generate_material")
    if material:
        _render_material(
            material=material,
            rag_info={
                "has_context": h.get("has_context", bool(material)),
                "sources_count": h.get("sources_count", 0),
                "query_used": h.get("query_used") or query,
            },
        )
    else:
        st.warning("⚠️ Data material tidak tersedia untuk riwayat ini.")

    st.divider()

    # ── Evaluasi RAGAS ────────────────────────────────────────────────────────
    _render_ragas_section(h)

    st.divider()

    # ── Raw Context (opsional, collapsible) ───────────────────────────────────
    retrieved_context = h.get("retrieved_context") or ""
    if retrieved_context:
        with st.expander("🗂️ Raw Context dari Knowledge Base", expanded=False):
            st.text_area(
                "Context",
                value=retrieved_context,
                height=200,
                disabled=True,
                label_visibility="collapsed",
            )