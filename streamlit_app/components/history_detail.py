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

import json
import streamlit as st
from components.audio_controls import (
    _inject_styles,
    _render_summary,
    _render_legal_qa,
    _render_risk_review,
    _render_clauses,
    _render_timeline,
    _render_comparisons,
    _render_referensi,
)


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
    try:
        v = float(value)
        if v >= good_thresh:
            bg, fg = "rgba(93,190,138,0.12)", "#5DBE8A"
        elif v >= warn_thresh:
            bg, fg = "rgba(232,147,74,0.12)", "#E8934A"
        else:
            bg, fg = "rgba(224,96,112,0.12)", "#E06070"
        display = f"{v:.2f}"
    except (TypeError, ValueError):
        bg, fg, display = "rgba(255,255,255,0.06)", "#A89F93", str(value) if value else "N/A"

    return (
        f'<span class="ragas-badge" '
        f'style="background:{bg};color:{fg};">'
        f'{_score_emoji(value) if value is not None else "⬜"} {label}: {display}</span>'
    )


# ── Render material ───────────────────────────────────────────────────────────
def _render_material(material: dict, rag_info: dict):
    sources_count = rag_info.get("sources_count", 0)
    has_context   = rag_info.get("has_context", False)
    query_used    = rag_info.get("query_used", "-")

    st.markdown(
        f'<div class="info-pill-container">'
        f'<span class="info-pill">🔍 {query_used or "—"}</span>'
        f'<span class="info-pill">📚 {sources_count} chunk ditemukan</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if not has_context or not material:
        st.warning(
            "⚠️ Tidak ditemukan referensi hukum yang relevan. "
            "Pastikan knowledge base sudah berisi dokumen hukum yang sesuai."
        )
        return

    _render_summary(material.get("summary") or {})
    _render_legal_qa(material.get("legal_qa") or [])
    _render_risk_review(material.get("risk_review") or {})
    _render_clauses(material.get("clause_search") or [])
    _render_timeline(material.get("timeline_extraction") or [])
    _render_comparisons(material.get("comparison") or [])
    _render_referensi(material.get("referensi_uu") or [])


# ── Render RAGAS metrics ──────────────────────────────────────────────────────
def _render_ragas_section(h: dict):
    ragas_st = h.get("ragas_status", "skipped")
    metrics  = h.get("ragas_metrics") or {}

    st.markdown('<div class="result-header">📊 Evaluasi RAGAS</div>', unsafe_allow_html=True)

    if ragas_st == "skipped":
        st.info("⬜ Evaluasi RAGAS tidak dijalankan untuk riwayat ini.")
        return

    if ragas_st == "error":
        st.error(f"⚠️ Evaluasi RAGAS gagal: {metrics.get('error', 'Unknown error')}")
        return

    faith    = metrics.get("faithfulness")
    relev    = metrics.get("answer_relevancy")
    risk_f   = metrics.get("risk_faithfulness")
    cp       = metrics.get("context_precision")
    cr       = metrics.get("context_recall")
    segments = metrics.get("answer_faithfulness_segment", [])

    badges_html = " &nbsp; ".join(filter(None, [
        _badge("Faithfulness",  faith,  0.8, 0.6),
        _badge("Relevancy",     relev,  0.8, 0.6),
        _badge("Risk Faith",    risk_f, 0.8, 0.6),
        _badge("Ctx Precision", cp,     0.8, 0.6) if cp is not None else None,
        _badge("Ctx Recall",    cr,     0.8, 0.6) if cr is not None else None,
    ]))
    st.markdown(badges_html, unsafe_allow_html=True)
    st.markdown("")

    def _fmt(v): return f"{float(v):.2f}" if v is not None else "N/A"

    cols = st.columns(5)
    cols[0].metric("Faithfulness",      _fmt(faith))
    cols[1].metric("Answer Relevancy",  _fmt(relev))
    cols[2].metric("Risk Faithfulness", _fmt(risk_f))
    cols[3].metric("Ctx Precision",     _fmt(cp))
    cols[4].metric("Ctx Recall",        _fmt(cr))

    if segments:
        st.markdown('<div class="section-label">🧩 Segmen Terevaluasi</div>', unsafe_allow_html=True)
        seg_labels = {"faithfulness": "📌 Summary", "qa": "❓ QA", "risk": "⚠️ Risk"}
        pills = " ".join(
            f'<span class="segment-pill">{seg_labels.get(s, s)}</span>'
            for s in segments
        )
        st.markdown(f'<div style="padding-top:8px;">{pills}</div>', unsafe_allow_html=True)


# ── Konten detail (dipakai oleh kedua mode render) ────────────────────────────
def _render_history_content(h: dict):
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

    query = h.get("search_query") or h.get("repaired_text") or "-"
    st.markdown('<div class="result-header">🔍 Pertanyaan / Query</div>', unsafe_allow_html=True)
    st.info(query)

    raw = h.get("raw_transcribe") or ""
    if raw and raw != query:
        with st.expander("📝 Transkripsi Asli"):
            st.write(raw)

    st.divider()

    st.markdown('<div class="result-header">📋 Hasil Analisis Hukum</div>', unsafe_allow_html=True)

    material = h.get("generate_material") or h.get("generated_material")
    if isinstance(material, str):
        try:
            material = json.loads(material)
        except json.JSONDecodeError:
            material = {"summary": {"overview": material}}

    if material:
        _render_material(
            material=material,
            rag_info={
                "has_context":   h.get("has_context", bool(material)),
                "sources_count": h.get("sources_count", 0),
                "query_used":    h.get("query_used") or query,
            },
        )
    else:
        st.warning("⚠️ Data material tidak tersedia untuk riwayat ini.")

    st.divider()

    _render_ragas_section(h)

    st.divider()

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


# ── FULL PAGE — dipanggil dari app.py sebelum layout utama ───────────────────
def render_history_detail_page():
    """
    Render halaman penuh detail riwayat.
    Menggantikan seluruh layout normal (sidebar + kolom + tab).
    Dipanggil dari app.py sebelum st.columns / st.tabs dirender,
    diikuti st.stop() agar layout normal tidak ikut dirender.
    """
    _inject_styles()

    h = st.session_state.get("selected_history")
    if not h:
        st.rerun()
        return

    # ── Sidebar: navigasi kembali + info ringkas ──────────────────────────────
    with st.sidebar:
        st.markdown(
            '<div class="ac-header">🧠 RAGNOZA</div>'
            '<div class="ac-subheader">AI Legal Assistant</div>',
            unsafe_allow_html=True,
        )
        st.divider()

        title = (
            h.get("session_title")
            or h.get("search_query")
            or "Detail Riwayat"
        )
        st.markdown(
            f'<div style="font-size:13px;color:var(--text-muted);'
            f'padding:4px 0 12px 0;line-height:1.5;">'
            f'📋 <b style="color:var(--text-primary);">{title[:60]}</b></div>',
            unsafe_allow_html=True,
        )

        if st.button("← Kembali", use_container_width=True, key="btn_back_history", type="primary"):
            st.session_state.pop("selected_history", None)
            st.session_state.pop("selected_history_id", None)
            st.rerun()

        st.divider()

        created = str(h.get("created_at", ""))[:16]
        kb      = h.get("knowledge_base", "-")
        status  = h.get("decision_status", "-")
        score   = h.get("compliance_score", "-")

        st.markdown(
            f'<div style="font-size:12px;color:var(--text-muted);line-height:2.2;">'
            f'🗂 <b>KB:</b> {kb}<br>'
            f'📅 <b>Dibuat:</b> {created}<br>'
            f'⚖️ <b>Status:</b> {status}<br>'
            f'🎯 <b>Score:</b> {score}'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Konten utama — diberi sedikit margin kiri-kanan ───────────────────────
    _, main_col, _ = st.columns([0.3, 9.4, 0.3])

    with main_col:
        st.markdown(
            '<div class="ac-header">📋 Detail Riwayat Generate</div>',
            unsafe_allow_html=True,
        )
        st.divider()
        _render_history_content(h)


# ── LEGACY — tetap ada agar tidak breaking jika masih ada pemanggilan lama ───
def render_history_detail():
    """
    Legacy: render di dalam tab (bukan full page).
    Migrasi ke render_history_detail_page() + routing di app.py.
    """
    _inject_styles()
    h = st.session_state.get("selected_history")

    if not h:
        st.markdown(
            '<div class="history-empty">'
            '<div class="history-empty-icon">📋</div>'
            '<p class="history-empty-text">Pilih riwayat dari sidebar untuk melihat detailnya.</p>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    col_title, col_back = st.columns([6, 1])
    with col_title:
        st.markdown('<div class="ac-header">📋 Detail Riwayat Generate</div>', unsafe_allow_html=True)
    with col_back:
        if st.button("✖ Tutup", use_container_width=True, key="btn_close_history"):
            st.session_state.pop("selected_history", None)
            st.session_state.pop("selected_history_id", None)
            st.rerun()

    st.divider()
    _render_history_content(h)