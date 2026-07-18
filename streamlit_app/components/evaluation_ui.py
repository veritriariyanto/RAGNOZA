    # components/evaluation_ui.py
import streamlit as st
import json
from api.evaluasi.evaluation_api import run_ragas_evaluation, run_ragas_reeval    

# =========================================
# EVALUATION SECTION (Moved Below Tabs)
# =========================================
def render_evaluation_section(data: dict, session_id: str):
        st.divider()
        ragas_status = data.get("ragas_status", "skipped")
        ragas_metrics = data.get("ragas_metrics")
        ragas_evals = data.get("ragas_evaluations", [])

        if ragas_status == "success" and ragas_metrics:
            st.markdown("### 📊 Evaluasi RAGAS")

            # 💡 TAMBAHAN: Panduan Singkat Tepat Sebelum Metrik Angka
            with st.expander("📖 Panduan & Cara Membaca Metrik Evaluasi Ragas", expanded=False):
                col_a, col_b = st.columns(2)

                with col_a:
                    st.markdown("""
                    Metrik Ragas dihitung dengan rentang **0.00 hingga 1.00** (Semakin mendekati 1.00, kualitas sistem RAG Anda semakin prima).
                    
                    * **✨ Faithfulness (Keandalan/Faktualitas):** Mengukur apakah jawaban LLM murni berbasis pada *Referensi Pasal* yang ditemukan di Qdrant. Skor rendah berarti LLM mulai berhalusinasi di luar konteks hukum yang valid.
                    * **🎯 Answer Relevancy (Kesesuaian Jawaban):** Mengukur seberapa relevan jawaban LLM terhadap inti pertanyaan user. Skor tinggi berarti jawaban langsung ke akar masalah tanpa bertele-tele.
                    * **🔍 Context Precision (Ketepatan Konteks):** Mengukur apakah dokumen/pasal hukum yang dicari di database berada di urutan teratas secara akurat (*Memerlukan Ground Truth*).
                    * **📚 Context Recall (Kelengkapan Konteks):** Mengukur apakah pasal yang ditemukan sudah lengkap untuk menjawab studi kasus hukum secara menyeluruh (*Memerlukan Ground Truth*).
                    """)
                with col_b:
                    st.info("""
                    **📊 Panduan Interpretasi Skor:** 
                    * 🟢 **≥ 0.85** : Sangat Baik  
                    * 🟡 **0.70 – 0.84** : Baik  
                    * 🟠 **0.50 – 0.69** : Cukup  
                    * 🔴 **< 0.50** : Perlu Perbaikan
                    """)

            col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
            with col_m1:
                fs = ragas_metrics.get("faithfulness_summary")
                st.metric("Faithfulness (Summary)",
                          f"{fs:.2f}" if fs is not None else "N/A")
            with col_m2:
                fqa = ragas_metrics.get("faithfulness_qa")
                st.metric("Faithfulness (QA)",
                          f"{fqa:.2f}" if fqa is not None else "N/A")
            with col_m3:
                st.metric("Answer Relevancy",
                          f"{(ragas_metrics.get('answer_relevancy') or 0):.2f}")
            with col_m4:
                st.metric("Context Precision",
                          f"{(ragas_metrics.get('context_precision') or 0):.2f}")
            with col_m5:
                st.metric("Context Recall",
                          f"{(ragas_metrics.get('context_recall') or 0):.2f}")

            risk_f = ragas_metrics.get("risk_faithfulness")
            if risk_f is not None:
                st.metric("Risk Faithfulness", f"{risk_f:.2f}")

        elif ragas_status == "error":
            st.warning(
                "⚠️ Evaluasi RAGAS gagal. Klik tombol di bawah untuk mencoba lagi.")
        else:
            st.info("Evaluasi RAGAS belum dijalankan untuk riwayat ini.")

        # Action buttons for evaluation
        eval_col1, eval_col2 = st.columns([1, 3])
        with eval_col1:
            if st.button(
                "📊 Evaluasi Sekarang" if ragas_status != "success" else "🔄 Evaluasi Ulang",
                key=f"btn_eval_{session_id}",
                use_container_width=True,
                type="primary" if ragas_status != "success" else "secondary",
            ):
                question = data.get("search_query") or data.get(
                    "repaired_text") or ""
                context = data.get("retrieved_context") or ""
                mat = data.get("generate_material") or data.get(
                    "generated_material") or {}
                if isinstance(mat, str):
                    try:
                        mat = json.loads(mat)
                    except json.JSONDecodeError:
                        mat = {}

                if not question or not context:
                    st.warning(
                        "⚠️ Data tidak lengkap untuk evaluasi (query atau konteks kosong).")
                else:
                    with st.spinner("⏳ Menjalankan evaluasi RAGAS... (1–5 menit)"):
                        eval_result = run_ragas_evaluation(
                            question=question,
                            context=context,
                            material_dict=mat,
                            history_id=session_id,
                        )
                    if eval_result.get("status") == "success":
                        st.success("✅ Evaluasi berhasil! Memuat ulang...")
                        st.session_state.pop("_db_history_cache", None)
                        st.rerun()
                    else:
                        st.error(
                            f"❌ Evaluasi gagal: {eval_result.get('error', 'Unknown error')}")

        with eval_col2:
            st.caption(
                "Evaluasi menghitung metrik: Faithfulness, Answer Relevancy, Context Precision, dan Context Recall menggunakan RAGAS.")

        # Ground truth re-evaluation (optional)
        has_precision = ragas_metrics and ragas_metrics.get(
            "context_precision") is not None if ragas_metrics else False

        expander_label = (
            "🔄 Evaluasi Ulang dengan Ground Truth" if has_precision
            else "➕ Tambah Ground Truth untuk Context Precision & Recall"
        )
        with st.expander(expander_label, expanded=False):
            if has_precision:
                st.info(
                    "✅ Sudah dievaluasi dengan ground truth. Isi ulang untuk evaluasi ulang dengan jawaban referensi baru.")
            else:
                st.caption(
                    "Ground truth adalah jawaban ideal/referensi dari legal expert. "
                    "Jika diisi, akan mengaktifkan 2 metrik tambahan: Context Precision dan Context Recall."
                )
            gt_input = st.text_area(
                "Ground Truth",
                placeholder="Masukkan jawaban referensi ideal dari legal expert...",
                height=100,
                key=f"gt_input_{session_id}",
            )
            if st.button(
                "🔄 Evaluasi dengan Ground Truth",
                key=f"btn_reeval_{session_id}",
                use_container_width=True,
            ):
                if not gt_input.strip():
                    st.warning("⚠️ Ground truth tidak boleh kosong.")
                else:
                    question = data.get("search_query") or data.get(
                        "repaired_text") or ""
                    context = data.get("retrieved_context") or ""
                    with st.spinner("⏳ Menjalankan evaluasi dengan ground truth..."):
                        reeval_result = run_ragas_reeval(
                            ground_truth=gt_input.strip(),
                            history_id=session_id,
                            question=question,
                            context=context,
                        )
                    if reeval_result.get("status") == "success":
                        st.success(
                            "✅ Evaluasi ground truth berhasil! Memuat ulang...")
                        st.session_state.pop("_db_history_cache", None)
                        st.rerun()
                    else:
                        st.error(
                            f"❌ Evaluasi gagal: {reeval_result.get('error', 'Unknown error')}")