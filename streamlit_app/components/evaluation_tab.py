# streamlit_app/components/evaluation_tab.py

import logging
import streamlit as st
from components.audio_controls import _inject_styles
from api.evaluasi.evaluation_api import run_ragas_evaluation, run_ragas_reeval  # ← fix folder
from utils.session import (
    get_last_rag_result,
    get_last_ragas_result,
    set_last_ragas_result,
)

logger = logging.getLogger(__name__)

# =============================================================================
# HELPERS VISUAL
# =============================================================================

def _score_color(score: float | None) -> str:
    if score is None: return "gray"
    if score >= 0.85: return "green"
    if score >= 0.70: return "yellow"
    if score >= 0.50: return "orange"
    return "red"

def _score_label(score: float | None) -> str:
    if score is None: return "N/A"
    if score >= 0.85: return "Sangat Baik"
    if score >= 0.70: return "Baik"
    if score >= 0.50: return "Cukup"
    return "Perlu Perbaikan"

def _score_emoji(score: float | None) -> str:
    if score is None: return "⬜"
    if score >= 0.85: return "🟢"
    if score >= 0.70: return "🟡"
    if score >= 0.50: return "🟠"
    return "🔴"


def _resolve_history_id(last_rag: dict | None) -> int | None:
    if last_rag and last_rag.get("history_id") is not None:
        return last_rag.get("history_id")
    return st.session_state.get("selected_history_id")


def _sync_history_cache_after_ragas_update(history_id: int | None, result: dict) -> None:
    if history_id is None or result.get("status") != "success":
        return

    selected = st.session_state.get("selected_history")
    if selected and selected.get("id") == history_id:
        selected["ragas_status"]  = "success"
        selected["ragas_metrics"] = result.get("metrics") or {}
        st.session_state["selected_history"] = selected

    st.session_state["_force_refresh_history"] = True
    st.session_state.pop("_db_history_cache", None)


def _render_metric_card(label: str, description: str, score: float | None, badge: str = ""):
    text = _score_label(score)
    disp = f"{score:.4f}" if score is not None else "—"

    if score is None:
        border_color = "rgba(150,150,150,0.25)"
        value_color  = "#888888"
        bg_color     = "rgba(150,150,150,0.05)"
        bar_color    = "#aaaaaa"
        emoji        = "⬜"
    elif score >= 0.85:
        border_color = "rgba(29,158,117,0.35)"
        value_color  = "#0F6E56"
        bg_color     = "rgba(29,158,117,0.07)"
        bar_color    = "#1D9E75"
        emoji        = "🟢"
    elif score >= 0.70:
        border_color = "rgba(239,159,39,0.35)"
        value_color  = "#BA7517"
        bg_color     = "rgba(239,159,39,0.07)"
        bar_color    = "#EF9F27"
        emoji        = "🟡"
    elif score >= 0.50:
        border_color = "rgba(232,147,74,0.35)"
        value_color  = "#993C1D"
        bg_color     = "rgba(232,147,74,0.07)"
        bar_color    = "#E8934A"
        emoji        = "🟠"
    else:
        border_color = "rgba(226,75,74,0.35)"
        value_color  = "#A32D2D"
        bg_color     = "rgba(226,75,74,0.07)"
        bar_color    = "#E24B4A"
        emoji        = "🔴"

    pct = int((score or 0) * 100)

    badge_html = (
        f'<span style="font-size:9.5px;padding:1px 6px;border-radius:4px;'
        f'background:rgba(55,138,221,0.12);color:#185FA5;margin-left:6px;'
        f'font-weight:400;text-transform:none;letter-spacing:0;">{badge}</span>'
    ) if badge else ""

    st.markdown(
        f"""
        <div style="border:0.5px solid {border_color};border-radius:12px;
                    padding:14px 16px;background:{bg_color};margin-bottom:4px;">
          <div style="font-size:11px;font-weight:500;letter-spacing:.06em;text-transform:uppercase;
                      color:var(--color-text-secondary);margin-bottom:8px;">
            {label}{badge_html}
          </div>
          <div style="font-size:26px;font-weight:500;color:{value_color};line-height:1;margin-bottom:6px;">
            {emoji} {disp}
          </div>
          <div style="height:4px;border-radius:2px;background:rgba(150,150,150,0.15);
                      overflow:hidden;margin-bottom:8px;">
            <div style="height:100%;width:{pct}%;border-radius:2px;background:{bar_color};"></div>
          </div>
          <div style="font-size:11px;color:var(--color-text-secondary);">{text} · {description}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def _render_metrics_display(metrics: dict):
    has_gt = metrics.get("context_precision") is not None

    if has_gt:
        col1, col2 = st.columns(2)
        with col1:
            _render_metric_card("Faithfulness",      "Faktual vs konteks",              metrics.get("faithfulness"))
            _render_metric_card("Context Precision", "Presisi konteks vs ground truth", metrics.get("context_precision"), badge="+ ground truth")
            _render_metric_card("Risk Faithfulness", "Faktualitas segmen risiko",        metrics.get("risk_faithfulness"))
        with col2:
            _render_metric_card("Answer Relevancy", "Relevansi jawaban",   metrics.get("answer_relevancy"))
            _render_metric_card("Context Recall",   "Kelengkapan konteks", metrics.get("context_recall"), badge="+ ground truth")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            _render_metric_card("Faithfulness",      "Faktual vs konteks",       metrics.get("faithfulness"))
        with col2:
            _render_metric_card("Answer Relevancy",  "Relevansi jawaban",        metrics.get("answer_relevancy"))
        with col3:
            _render_metric_card("Risk Faithfulness", "Faktualitas segmen risiko", metrics.get("risk_faithfulness"))

    # Segmen pills
    segments = metrics.get("evaluated_segments", [])
    if segments:
        seg_labels = {"faithfulness": "📌 Summary", "qa": "❓ QA", "risk": "⚠️ Risk"}
        pills = " ".join(
            f'<span style="display:inline-block;font-size:11px;padding:3px 10px;border-radius:6px;'
            f'background:rgba(55,138,221,0.1);color:#185FA5;margin-right:4px;">'
            f'{seg_labels.get(s, s)}</span>'
            for s in segments
        )
        st.markdown(f'<div style="padding-top:4px;">{pills}</div>', unsafe_allow_html=True)

# =============================================================================
# MAIN RENDER
# =============================================================================

def render_evaluation_tab():
    _inject_styles()

    st.markdown(
        """
        <div class="ac-header">📊 Evaluasi RAGAS</div>
        <div class="ac-subheader">
            Evaluasi kualitas jawaban RAG. Tab ini auto-populate dari hasil audio terakhir.
            Isi <strong>ground truth</strong> untuk mengaktifkan Context Precision &amp; Recall.
        </div>
        <div class="ac-divider"></div>
        """,
        unsafe_allow_html=True,
    )

    # ── Panduan metrik ────────────────────────────────────────────────────────
    with st.expander("📖 Panduan Metrik RAGAS", expanded=False):
        col_a, col_b = st.columns(2)
        
        with col_a:
            st.markdown("""
            ### 🎯 Jawaban (Generation)
            
            **Faithfulness** *Seberapa faktual jawaban berdasarkan konteks yang diberikan.* 💡 *Skor tinggi:* Jawaban tidak mengandung informasi di luar konteks.
            
            ---
            
            **Context Precision** <span style='color: #ff4b4b;'>(Butuh Ground Truth)</span>  
            *Seberapa relevan konteks yang di-retrieve.* 💡 *Skor tinggi:* Konteks paling relevan muncul di urutan atas.
            """, unsafe_allow_html=True)
            
        with col_b:
            st.markdown("""
            ### 🔍 Konteks (Retrieval)
            
            **Answer Relevancy** *Seberapa baik jawaban menjawab pertanyaan pengguna.* 💡 *Skor tinggi:* Jawaban fokus pada inti pertanyaan.
            
            ---
            
            **Context Recall** <span style='color: #ff4b4b;'>(Butuh Ground Truth)</span>  
            *Seberapa lengkap konteks mencakup informasi yang diperlukan.* 💡 *Skor tinggi:* Tidak ada informasi penting yang terlewat.
            """, unsafe_allow_html=True)
            
        st.divider()
        
        # Menggunakan st.info agar bagian interpretasi memiliki background card yang rapi
        st.info("""
        **📊 Panduan Interpretasi Skor:** * 🟢 **≥ 0.85** : Sangat Baik  
        * 🟡 **0.70 – 0.84** : Baik  
        * 🟠 **0.50 – 0.69** : Cukup  
        * 🔴 **< 0.50** : Perlu Perbaikan
        """)

    st.divider()

    # ── Ambil state ───────────────────────────────────────────────────────────
    last_rag   = get_last_rag_result()
    last_ragas = get_last_ragas_result()

    last_rag   = last_rag   if isinstance(last_rag,   dict) else None
    last_ragas = last_ragas if isinstance(last_ragas, dict) else None

    # ── Tampilkan hasil otomatis ──────────────────────────────────────────────
    if last_rag and last_ragas and last_ragas.get("status") == "success":
        ts = last_ragas.get("timestamp", "-")
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;justify-content:space-between;
                        padding:10px 16px;background:var(--color-background-secondary);
                        border:0.5px solid rgba(150,150,150,0.25);border-radius:12px;
                        margin-bottom:14px;">
            <span style="font-size:13px;font-weight:500;color:var(--color-text-primary);">
                Hasil evaluasi otomatis
            </span>
            <span style="font-size:11px;color:var(--color-text-secondary);">{ts}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        metrics = last_ragas.get("metrics", {})
        _render_metrics_display(metrics)

        # ── Ground truth ──────────────────────────────────────────────────────
        st.divider()
        has_gt_already = metrics.get("context_precision") is not None

        if has_gt_already:
            st.info("✅ Sudah dievaluasi dengan ground truth (4 metrik aktif). Isi ulang untuk evaluasi ulang.")
        else:
            st.caption("Saat ini hanya 2 metrik. Isi ground truth untuk aktifkan Context Precision & Recall.")

        gt_input = st.text_area(
            "Ground truth",
            placeholder="Masukkan jawaban referensi ideal...",
            height=100,
            key="gt_from_auto",
        )

        if st.button("🔄 Evaluasi ulang dengan ground truth", key="btn_reeval"):
            if not gt_input.strip():
                st.warning("⚠️ Ground truth tidak boleh kosong.")
            elif not last_rag:
                st.warning("⚠️ Tidak ada data RAG tersimpan. Proses audio terlebih dahulu.")
            else:
                with st.spinner("⏳ Menjalankan evaluasi ulang RAGAS..."):
                    history_id = _resolve_history_id(last_rag)
                    new_result = run_ragas_reeval(
                        ground_truth=gt_input.strip(),
                        history_id=history_id,
                        question=last_rag.get("question"),
                        context=last_rag.get("context"),
                    )
                set_last_ragas_result(new_result)
                _sync_history_cache_after_ragas_update(history_id, new_result)
                st.rerun()

        with st.expander("🔍 Detail input yang dievaluasi", expanded=False):
            st.markdown(f"**Pertanyaan:** {last_rag.get('question', '-')}")
            ctx = last_rag.get("context", "")
            st.markdown("**Konteks:**")
            st.info(ctx[:800] + ("..." if len(ctx) > 800 else ""))
            st.markdown("**Jawaban LLM:**")
            st.info(last_rag.get("generated_material", {}))

    elif last_ragas and last_ragas.get("status") == "error":
        st.error(f"⚠️ Evaluasi otomatis gagal: {last_ragas.get('error', 'Unknown error')}")
        st.info("Gunakan form di bawah untuk evaluasi manual.")

    else:
        st.info("💡 Belum ada hasil evaluasi. Proses audio di tab Audio terlebih dahulu.")