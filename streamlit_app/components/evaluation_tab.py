# evaluation_tab.py

"""
streamlit_app/components/evaluation_tab.py  (updated)
 
Perubahan dari versi lama:
- Auto-populate form dari hasil RAG terakhir (session_state.last_rag_result)
- Tampilkan hasil RAGAS otomatis jika sudah ada (session_state.last_ragas_result)
- Form manual tetap tersedia untuk evaluasi kustom atau tambah ground truth
- Tombol "Evaluasi Ulang dengan Ground Truth" untuk aktifkan 4 metrik
"""

import streamlit as st
from api.evaluasi.evaluation_api import run_ragas_evaluation
from utils.session import (
    get_last_rag_result,
    get_last_ragas_result,
    set_last_ragas_result,
)

# ─────────────────────────────────────────
# HELPERS VISUAL
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


def _resolve_history_id(last_rag: dict | None) -> int | None:
    if last_rag and last_rag.get("history_id") is not None:
        return last_rag.get("history_id")
    return st.session_state.get("selected_history_id")


def _sync_history_cache_after_ragas_update(history_id: int | None, result: dict) -> None:
    if history_id is None:
        return
    if result.get("status") != "success":
        return

    selected = st.session_state.get("selected_history")
    if selected and selected.get("id") == history_id:
        selected["ragas_status"] = "success"
        selected["ragas_metrics"] = result.get("metrics") or {}
        st.session_state["selected_history"] = selected

    st.session_state["_force_refresh_history"] = True
    st.session_state.pop("_db_history_cache", None)


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

def _render_metrics_display(metrics: dict):
    """Render kartu metrik + progress bar dari dict metrics."""
    has_gt = metrics.get("context_precision") is not None

    if has_gt: 
        col1, col2 = st.columns(2)
        with col1:
            _render_metric_card("Faithfulness",      "Faktual vs konteks",          metrics.get("faithfulness"))
            _render_metric_card("Context Precision", "Presisi konteks vs reference", metrics.get("context_precision"), badge="+ ground truth")
        with col2:
            _render_metric_card("Answer Relevancy",  "Relevansi jawaban",           metrics.get("answer_relevancy"))
            _render_metric_card("Context Recall",    "Kelengkapan konteks",         metrics.get("context_recall"),    badge="+ ground truth")

            st.markdown("<div style='margin-top:8px;'>", unsafe_allow_html=True)
            _render_metric_card("Overall Score", "Rata-rata semua 4 metrik", metrics.get("overall_score"))
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        col1, col2, col3 = st.columns(3)  
        with col1:
            _render_metric_card("Faithfulness",     "Faktual vs konteks", metrics.get("faithfulness"))
        with col2:
            _render_metric_card("Answer Relevancy", "Relevansi jawaban",  metrics.get("answer_relevancy"))
        with col3:
            _render_metric_card("Overall Score",    "Rata-rata 2 metrik", metrics.get("overall_score"))

    # Progress bar
    st.markdown("#### 📈 Visualisasi Skor")
    for name, score in [
        ("Faithfulness", metrics.get("faithfulness")),
        ("Answer Relevancy", metrics.get("answer_relevancy")),
        ("Context Precision", metrics.get("context_precision")),
        ("Context Recall", metrics.get("context_recall")),
    ]:
        if score is not None:
            col_label, col_bar = st.columns([1.5, 3])
            with col_label:
                st.markdown(
                    f"<div style='padding-top:6px; font-size:13px;'>"
                    f"{_score_emoji(score)} <b>{name}</b></div>",
                    unsafe_allow_html=True,
                )
            with col_bar:
                st.progress(float(score), text=f"{score:.4f}")

    #Rekomendasi
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
                "❌ **Performa rendah, perlu peningkatan.** "
                "Analisis lebih lanjut diperlukan untuk mengidentifikasi penyebab."
            )

# ─────────────────────────────────────────
# MAIN RENDER
# ─────────────────────────────────────────

def render_evaluation_tab():
    st.subheader("📊 **Evaluasi RAGAS**")
    st.caption(
        "Evaluasi kualitas jawaban RAG. Tab ini auto-populate dari hasil audio terakhir. "
        "Isi **ground truth** untuk mengaktifkan Context Precision & Recall."
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
            "**Interpretasi:** " \
            "🟢 `≥ 0.8` Sangat Baik &nbsp; "
            "🟡 `0.6–0.79` Cukup Baik &nbsp; " \
            "🔴 `< 0.6` Perlu Perbaikan"
        )

    # ── SEKSI 1: HASIL OTOMATIS (dari RAG pipeline terakhir) ─────────────────
    last_rag = get_last_rag_result()
    last_ragas = get_last_ragas_result()

    # Normalisasi — pastikan keduanya dict atau None
    last_rag   = last_rag   if isinstance(last_rag,   dict) else None
    last_ragas = last_ragas if isinstance(last_ragas, dict) else None

    if last_rag and last_ragas and isinstance(last_ragas, dict) and last_ragas.get("status") == "success":
        st.markdown("### 🤖 Evaluasi Otomatis — Hasil Terakhir") 

        timestamp = last_ragas.get("timestamp", "-") if last_ragas else "-"
        question  = last_rag.get("question", "-")[:80] if last_rag else "-"
        st.caption(f"Dari audio diproses pukul **{timestamp}** · Query: *{question}...*")

        metrics = last_ragas.get("metrics", {})
        _render_metrics_display(metrics)

        # ── Tambah Ground Truth untuk 4 Metrik ───────────────────────────────
        st.divider()
        st.markdown("#### ➕ Tambah Ground Truth untuk 4 Metrik")
        # SESUDAH — cek dulu apakah sudah ada context_precision:
        has_gt_already = metrics.get("context_precision") is not None
        if has_gt_already:
            st.caption(
                "✅ Sudah dievaluasi dengan ground truth (4 metrik aktif). "
                "Isi ulang untuk evaluasi dengan ground truth berbeda."
            )
        else:
            st.caption(
                "Saat ini hanya 2 metrik (tanpa ground truth). "
                "Isi di bawah untuk aktifkan Context Precision & Context Recall."
            )

        gt_input = st.text_area(
            "✅ Ground Truth",
            placeholder="Masukkan jawaban referensi ideal untuk pertanyaan di atas...",
            height=100,
            key="gt_from_auto",
        )

        if st.button("🔄 Evaluasi Ulang dengan Ground Truth", key="btn_reeval"):
            if not gt_input.strip():
                st.warning("⚠️ Ground truth tidak boleh kosong untuk evaluasi ulang.")
            elif not last_rag:
                st.warning("⚠️ Tidak ada data RAG tersimpan. Proses audio terlebih dahulu.")
            else:
                with st.spinner("⏳ Menjalankan evaluasi ulang RAGAS..."):
                    history_id = _resolve_history_id(last_rag)
                    new_result = run_ragas_evaluation(
                        question=last_rag["question"],
                        context=last_rag["context"],
                        answer=last_rag["answer_text"],
                        ground_truth=gt_input.strip(),
                        history_id=history_id,
                    )
                set_last_ragas_result(new_result)  # Update hasil evaluasi di session
                _sync_history_cache_after_ragas_update(history_id, new_result)
                st.rerun()  # Refresh untuk tampilkan hasil baru

        # Detail input
        if last_rag:
            with st.expander("🔍 Detail Input yang Dievaluasi", expanded=False):
                st.markdown(f"**❓ Pertanyaan:** {last_rag.get('question', '-')}")
                st.markdown("**📄 Konteks:**")
                st.info(last_rag.get("context", "-")[:800] + ("..." if len(last_rag.get("context", "")) > 800 else ""))
                st.markdown("**💡 Jawaban LLM:**")
                st.success(last_rag.get("answer_text", "-")[:600])

    elif last_ragas and last_ragas.get("status") == "error":
        st.error(f"⚠️ Evaluasi otomatis terakhir gagal: {last_ragas.get('error', 'Unknown error')}")
        st.info("Gunakan form di bawah untuk evaluasi manual.")

    else:
        st.info(
            "💡 Belum ada hasil evaluasi otomatis. "
            "Proses audio di **tab Generate** dengan tombol 🚀 **Proses RAG & Evaluasi** terlebih dahulu."
        )

    # ── SEKSI 2: FORM MANUAL ──────────────────────────────────────────────────
    st.divider()
    st.markdown("### 📝 Input Evaluasi Manual")
    st.caption("Evaluasi kustom dengan input manual.")

    # Pre-fill dari last_rag jika ada, tapi bisa diedit
    default_question = last_rag["question"] if last_rag else ""
    default_context  = last_rag["context"] if last_rag else ""
    default_answer   = last_rag["answer_text"] if last_rag else ""

    with st.form("ragas_evaluation_form", clear_on_submit=False):

        question_input = st.text_area(
            "❓ Pertanyaan",
            value=default_question,
            placeholder="Contoh: Apa bunyi Pasal 1 UUD 1945?",
            height=80,
            help="Pertanyaan yang diajukan user ke sistem RAG.",
        )

        context_input = st.text_area(
            "📄 Konteks (Retrieved Context)",
            value=default_context,
            placeholder="Teks konteks yang di-retrieve dari knowledge base...",
            height=120,
            help="Chunk teks yang dikembalikan oleh retriever.",
        )

        answer_input = st.text_area(
            "💡 Jawaban LLM",
            value=default_answer,
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
        st.markdown("### 📊 Hasil Evaluasi Manual")

        with st.spinner("⏳ Menjalankan evaluasi RAGAS... (biasanya 15–60 detik)"):
            history_id = _resolve_history_id(last_rag)
            result = run_ragas_evaluation(
                question=question_input.strip(),
                context=context_input.strip(),
                answer=answer_input.strip(),
                ground_truth=ground_truth_input.strip() or None,
                history_id=history_id,
            )

        if result.get("status") == "error":
            st.error(f"❌ Evaluasi gagal: {result.get('error', 'Unknown error')}")
            return

        _sync_history_cache_after_ragas_update(history_id, result)
        _render_metrics_display(result.get("metrics", {}))