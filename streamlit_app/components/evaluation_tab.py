# evaluation_tab.py

import streamlit as st
from api.evaluasi.evaluation_api import run_ragas_evaluation


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def _score_color(score: float | None) -> str:
    if score is None: return "gray"
    if score >= 0.8:  return "green"
    if score >= 0.6:  return "orange"
    return "red"

def _score_label(score: float | None) -> str:
    if score is None: return "N/A"
    if score >= 0.8:  return "Sangat Baik"
    if score >= 0.6:  return "Cukup Baik"
    return "Perlu Perbaikan"

def _score_emoji(score: float | None) -> str:
    if score is None: return "⬜"
    if score >= 0.8:  return "🟢"
    if score >= 0.6:  return "🟡"
    return "🔴"

def _border_color(color: str) -> str:
    return {
        "green":  "#28a745",
        "orange": "#fd7e14",
        "red":    "#dc3545",
        "gray":   "#6c757d",
    }.get(color, "#6c757d")

def _bg_color(color: str) -> str:
    return {
        "green":  "rgba(40,167,69,0.05)",
        "orange": "rgba(253,126,20,0.05)",
        "red":    "rgba(220,53,69,0.05)",
        "gray":   "rgba(108,117,125,0.05)",
    }.get(color, "rgba(108,117,125,0.05)")


def _render_metric_card(label: str, description: str, score: float | None, badge: str = ""):
    color  = _score_color(score)
    emoji  = _score_emoji(score)
    text   = _score_label(score)
    disp   = f"{score:.4f}" if score is not None else "—"
    border = _border_color(color)
    bg     = _bg_color(color)

    badge_html = (
        f'<span style="font-size:10px; background:#444; color:#ccc; '
        f'border-radius:4px; padding:1px 6px; margin-left:6px;">{badge}</span>'
        if badge else ""
    )

    st.markdown(
        f"""
        <div style="border:1px solid {border}; border-radius:10px; padding:16px 20px;
                    background:{bg}; margin-bottom:4px;">
            <div style="font-size:13px; color:#888; margin-bottom:4px;">
                {label}{badge_html}
            </div>
            <div style="font-size:28px; font-weight:700; color:{border};">
                {emoji} {disp}
            </div>
            <div style="font-size:12px; color:#aaa; margin-top:4px;">
                {text} · {description}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────
# MAIN RENDER
# ─────────────────────────────────────────

def render_evaluation_tab():
    st.subheader("📊 **Evaluasi RAGAS**")
    st.caption(
        "Evaluasi kualitas jawaban RAG. Isi **ground truth** untuk mengaktifkan "
        "metrik Context Precision & Context Recall."
    )

    st.divider()

    # ── PANDUAN METRIK ──────────────────────────────────
    with st.expander("📖 Panduan Metrik RAGAS", expanded=False):
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("""
**🎯 Faithfulness**  
Seberapa faktual jawaban berdasarkan konteks.  
Skor tinggi = jawaban tidak "mengarang" di luar konteks.

**📐 Context Precision** *(butuh ground truth)*  
Seberapa presisi konteks yang di-retrieve.  
Skor tinggi = chunk yang relevan muncul di posisi atas.
            """)
        with col_b:
            st.markdown("""
**💬 Answer Relevancy**  
Seberapa relevan jawaban terhadap pertanyaan.  
Skor tinggi = jawaban langsung menjawab inti pertanyaan.

**🔁 Context Recall** *(butuh ground truth)*  
Seberapa lengkap konteks mencakup ground truth.  
Skor tinggi = tidak ada informasi penting yang terlewat.
            """)
        st.markdown(
            "**Interpretasi:** 🟢 `≥ 0.8` Sangat Baik &nbsp; "
            "🟡 `0.6–0.79` Cukup Baik &nbsp; 🔴 `< 0.6` Perlu Perbaikan"
        )

    # ── FORM INPUT ──────────────────────────────────────
    st.markdown("### 📝 Input Evaluasi")

    with st.form("ragas_evaluation_form", clear_on_submit=False):

        question_input = st.text_area(
            "❓ Pertanyaan",
            placeholder="Contoh: Apa bunyi Pasal 1 UUD 1945?",
            height=80,
            help="Pertanyaan yang diajukan user ke sistem RAG.",
        )

        context_input = st.text_area(
            "📄 Konteks (Retrieved Context)",
            placeholder="Teks konteks yang di-retrieve dari knowledge base...",
            height=120,
            help="Chunk teks yang dikembalikan oleh retriever.",
        )

        answer_input = st.text_area(
            "💡 Jawaban LLM",
            placeholder="Jawaban yang dihasilkan LLM berdasarkan konteks...",
            height=120,
            help="Output dari LLM setelah menerima konteks dan pertanyaan.",
        )

        # Ground truth — opsional tapi membuka metrik tambahan
        ground_truth_input = st.text_area(
            "✅ Ground Truth *(opsional — aktifkan Context Precision & Recall)*",
            placeholder="Contoh: Berdasarkan Pasal 1 UUD 1945, Indonesia adalah Negara Kesatuan berbentuk Republik.",
            height=100,
            help="Jawaban referensi ideal. Jika diisi, 4 metrik dievaluasi. Jika kosong, hanya 2 metrik.",
        )

        has_ground_truth = bool(ground_truth_input.strip())

        # Info badge metrik aktif
        if has_ground_truth:
            st.info("✅ Ground truth terdeteksi — **4 metrik** akan dievaluasi: Faithfulness, Answer Relevancy, Context Precision, Context Recall.")
        else:
            st.warning("⚠️ Tanpa ground truth — **2 metrik** yang dievaluasi: Faithfulness, Answer Relevancy.")

        submitted = st.form_submit_button(
            "🚀 Jalankan Evaluasi",
            use_container_width=True,
            type="primary",
        )

    # ── PROSES & HASIL ──────────────────────────────────
    if submitted:
        if not question_input.strip():
            st.warning("⚠️ Pertanyaan tidak boleh kosong.")
            return
        if not context_input.strip():
            st.warning("⚠️ Konteks tidak boleh kosong.")
            return
        if not answer_input.strip():
            st.warning("⚠️ Jawaban LLM tidak boleh kosong.")
            return

        st.divider()
        st.markdown("### 📊 Hasil Evaluasi")

        with st.spinner("⏳ Menjalankan evaluasi RAGAS... (biasanya 15–60 detik)"):
            result = run_ragas_evaluation(
                question=question_input.strip(),
                context=context_input.strip(),
                answer=answer_input.strip(),
                ground_truth=ground_truth_input.strip() or None,
            )

        if result.get("status") == "error":
            st.error(f"❌ Evaluasi gagal: {result.get('error', 'Unknown error')}")
            return

        metrics = result.get("metrics", {})
        has_gt_result = metrics.get("context_precision") is not None

        # ── KARTU METRIK ──
        if has_gt_result:
            # 4 kartu dalam 2 baris
            col1, col2 = st.columns(2)
            with col1:
                _render_metric_card("Faithfulness",      "Faktual vs konteks",          metrics.get("faithfulness"))
                _render_metric_card("Context Precision", "Presisi konteks vs reference", metrics.get("context_precision"), badge="+ ground truth")
            with col2:
                _render_metric_card("Answer Relevancy",  "Relevansi jawaban",           metrics.get("answer_relevancy"))
                _render_metric_card("Context Recall",    "Kelengkapan konteks",         metrics.get("context_recall"),    badge="+ ground truth")

            # Overall sendiri di bawah
            st.markdown("<div style='margin-top:8px;'>", unsafe_allow_html=True)
            _render_metric_card("Overall Score", "Rata-rata semua 4 metrik", metrics.get("overall_score"))
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            # 2 kartu + overall
            col1, col2, col3 = st.columns(3)
            with col1:
                _render_metric_card("Faithfulness",     "Faktual vs konteks", metrics.get("faithfulness"))
            with col2:
                _render_metric_card("Answer Relevancy", "Relevansi jawaban",  metrics.get("answer_relevancy"))
            with col3:
                _render_metric_card("Overall Score",    "Rata-rata 2 metrik", metrics.get("overall_score"))

        # ── PROGRESS BAR ──
        st.markdown("#### 📈 Visualisasi Skor")

        metrics_display = {
            "Faithfulness":      metrics.get("faithfulness"),
            "Answer Relevancy":  metrics.get("answer_relevancy"),
            "Context Precision": metrics.get("context_precision"),
            "Context Recall":    metrics.get("context_recall"),
        }

        for metric_name, score in metrics_display.items():
            if score is not None:
                col_label, col_bar = st.columns([1.5, 3])
                with col_label:
                    st.markdown(
                        f"<div style='padding-top:6px; font-size:13px;'>"
                        f"{_score_emoji(score)} <b>{metric_name}</b></div>",
                        unsafe_allow_html=True,
                    )
                with col_bar:
                    st.progress(float(score), text=f"{score:.4f}")

        # ── DETAIL INPUT ──
        with st.expander("🔍 Detail Input yang Dievaluasi", expanded=False):
            inp = result.get("input", {})
            st.markdown(f"**❓ Pertanyaan:** {inp.get('question', '-')}")
            st.markdown("**📄 Konteks:**")
            st.info(inp.get("context", "-"))
            st.markdown("**💡 Jawaban LLM:**")
            st.success(inp.get("answer", "-"))
            if inp.get("ground_truth"):
                st.markdown("**✅ Ground Truth:**")
                st.warning(inp.get("ground_truth"))

        # ── REKOMENDASI ──
        overall = metrics.get("overall_score")
        if overall is not None:
            st.divider()
            if overall >= 0.8:
                st.success(
                    "✅ **Sistem RAG Anda bekerja dengan sangat baik!** "
                    "Jawaban akurat, faktual, dan relevan."
                )
            elif overall >= 0.6:
                st.warning(
                    "⚠️ **Performa cukup, ada ruang perbaikan.** "
                    "Pertimbangkan meningkatkan kualitas chunk atau sistem prompt."
                )
            else:
                st.error(
                    "🔴 **Performa perlu ditingkatkan.** "
                    "Coba perbaiki strategi retrieval, kualitas dokumen, atau instruksi system prompt."
                )