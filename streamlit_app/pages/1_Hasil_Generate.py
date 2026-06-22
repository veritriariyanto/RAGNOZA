# streamlit_app/pages/1_Hasil_Generate.py

import streamlit as st
import json  # 🛠️ Tambahkan import ini untuk membongkar string JSON
from api.history.history_api import get_history_by_id, get_all_history
from api.evaluasi.evaluation_api import run_ragas_evaluation
from components.left_sidebar import render_left_sidebar
from utils.session import init_session_state

# Inisialisasi session state agar sidebar tidak error saat properti belum ada
init_session_state()

# =========================================
# PAGE CONFIG
# =========================================
st.set_page_config(
    page_title="Hasil Generate - RAGNOZA",
    page_icon="📊",
    layout="wide"
)

# =========================================
# SIDEBAR
# =========================================
with st.sidebar:
    render_left_sidebar()

# =========================================
# MAIN CONTENT
# =========================================
st.title("📊 Dashboard Hasil Analisis")
st.caption("Halaman Khusus Detail Eksklusif Hasil Generate RAG & LLM")
st.divider()

# 1. Resolve which history ID to display
#    Priority: sidebar click → new RAG pipeline → latest history
session_id = (
    st.session_state.get("selected_history_id")
    or st.session_state.get("current_session_id")
)

if not session_id:
    res_all = get_all_history()
    if res_all.get("status") == "success" and res_all.get("data"):
        session_id = res_all["data"][0]["id"]

# 2. Tarik detail data dari database
if session_id:
    res = get_history_by_id(session_id)

    if res.get("status") == "success":
        data = res.get("data")
        material = data.get("generate_material") or data.get(
            "generated_material") or {}
        if isinstance(material, str):
            try:
                material = json.loads(material)
            except json.JSONDecodeError:
                material = {"summary": {"overview": material}}

        # =========================================
        # HEADER INFORMASI KASUS
        # =========================================
        case_title = data.get('title') or data.get(
            'session_title') or 'Analisis Tanpa Judul'
        st.subheader(f"📁 {case_title}")
        st.caption(
            f"Waktu Eksekusi: {data.get('created_at')} | STT Provider: {data.get('provider')}")

        st.divider()

        # =========================================
        # EVALUATION SECTION (Prominent Display)
        # =========================================
        ragas_status = data.get("ragas_status", "skipped")
        ragas_metrics = data.get("ragas_metrics")
        ragas_evals = data.get("ragas_evaluations", [])

        if ragas_status == "success" and ragas_metrics:
            st.markdown("### 📊 Evaluasi RAGAS")
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            with col_m1:
                st.metric("Faithfulness",
                          f"{(ragas_metrics.get('faithfulness') or 0):.2f}")
            with col_m2:
                st.metric("Answer Relevancy",
                          f"{(ragas_metrics.get('answer_relevancy') or 0):.2f}")
            with col_m3:
                st.metric("Context Precision",
                          f"{(ragas_metrics.get('context_precision') or 0):.2f}")
            with col_m4:
                st.metric("Context Recall",
                          f"{(ragas_metrics.get('context_recall') or 0):.2f}")

            # Risk faithfulness if available
            risk_f = ragas_metrics.get("risk_faithfulness")
            if risk_f is not None:
                st.metric("Risk Faithfulness", f"{risk_f:.2f}")

        elif ragas_status == "error":
            st.warning(
                "⚠️ Evaluasi RAGAS gagal. Klik tombol di bawah untuk mencoba lagi.")

        else:
            st.info("Evaluasi RAGAS belum dijalankan untuk riwayat ini.")

        # Evaluation button (always visible)
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

        st.divider()

        # =========================================
        # KOMPONEN 6 TABS UTAMA (Bebas dari Bungkus JSON)
        # =========================================
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📝 Ringkasan", "⚠️ Risiko", "❓ Q&A",
            "📂 Pasal", "🗣️ Transkripsi", "⚙️ Raw Log"
        ])

        # --- TAB 1: SUMMARY ---
        with tab1:
            st.write("### 📝 Ringkasan Kasus Eksekutif")
            summary_raw = material.get("summary")

            # Deteksi jika summary_raw dikirim berupa JSON String/Dict oleh backend
            if isinstance(summary_raw, str) and summary_raw.strip().startswith("{"):
                try:
                    summary_raw = json.loads(summary_raw)
                except:
                    pass

            if isinstance(summary_raw, dict):
                st.markdown(
                    f"#### **Overview**\n{summary_raw.get('overview', '')}")
                st.markdown(
                    f"#### **Conclusion**\n{summary_raw.get('conclusion', '')}")
                if summary_raw.get("key_points"):
                    st.markdown("#### **Key Points:**")
                    for point in summary_raw["key_points"]:
                        st.markdown(f"- {point}")
            elif isinstance(summary_raw, str):
                st.markdown(summary_raw)
            else:
                st.warning(
                    "Tidak ada ringkasan teks yang dihasilkan oleh LLM.")

        # --- TAB 2: RISK REVIEW ---
        with tab2:
            st.write("### ⚠️ Review Risiko Finansial & Hukum")
            risk_raw = material.get("risk_review")

            # 1. Jika datanya string JSON, bongkar dulu menjadi Dictionary Python
            if isinstance(risk_raw, str):
                risk_raw = risk_raw.strip()
                if risk_raw.startswith("{"):
                    try:
                        risk_raw = json.loads(risk_raw)
                    except:
                        pass

            # 2. Render jika data berupa Dictionary (Sesuai dengan JSON asli database)
            if isinstance(risk_raw, dict):
                # Baris metrik status dan skor risiko
                col_r1, col_r2 = st.columns(2)
                with col_r1:
                    status_risiko = risk_raw.get("status", "N/A")
                    st.metric(label="Status Risiko", value=status_risiko)
                with col_r2:
                    skor_risiko = risk_raw.get("score", 0)
                    st.metric(label="Skor Tingkat Risiko",
                              value=f"{skor_risiko}/100")

                st.divider()

                # Tampilkan text analisis utama
                if risk_raw.get("analysis"):
                    st.markdown(
                        f"#### 🔍 Analisis Mendalam:\n{risk_raw.get('analysis')}")

                # Tampilkan daftar list point-point risiko
                risks_list = risk_raw.get("risks", [])
                if risks_list:
                    st.markdown("#### 🚨 Daftar Bahaya Risiko yang Terdeteksi:")
                    for idx, rsk in enumerate(risks_list, 1):
                        rsk_clean = str(rsk).replace('[', '').replace(']', '').replace('"', '')
                        st.error(f"**{idx}.** {rsk_clean}")

                # Tampilkan rekomendasi tindakan
                if risk_raw.get("recommendation"):
                    st.warning(
                        f"💡 **Rekomendasi Utama:** {risk_raw.get('recommendation')}")

                # Tampilkan langkah mitigasi pencegahan
                mitigasi_list = risk_raw.get("mitigation_steps", [])
                if mitigasi_list:
                    st.markdown("#### 🛡️ Langkah Mitigasi / Pencegahan:")
                    for idx, mit in enumerate(mitigasi_list, 1):
                        mit_clean = str(mit).replace('[', '').replace(']', '').replace('"', '')
                        st.info(f"**Langkah {idx}:** {mit_clean}")

            # 3. Fallback jika strukturnya berupa list murni (antisipasi legacy data)
            elif isinstance(risk_raw, list):
                for index, risk in enumerate(risk_raw, 1):
                    risk_str = str(risk).replace("[", "").replace(
                        "]", "").replace('"', '').replace("'", "")
                    if risk_str.strip():
                        st.error(f"**Risiko #{index}:** {risk_str}")

            else:
                st.warning(
                    "Data analisis risiko kosong atau tidak kompatibel dengan format sistem.")

        # --- TAB 4: LEGAL QA (Rekomendasi Tindakan) ---
        with tab3:
            st.write("### ❓ Rekomendasi Tindakan (Q&A/Saran)")
            legal_qa_raw = material.get("legal_qa")

            # Deteksi jika data berupa array string ["Pastikan ada bukti...", "Jangan memaksakan..."]
            if isinstance(legal_qa_raw, str) and legal_qa_raw.strip().startswith("["):
                try:
                    legal_qa_raw = json.loads(legal_qa_raw)
                except:
                    pass

            if isinstance(legal_qa_raw, list):
                st.markdown("#### 💡 Langkah/Saran Strategis Hukum:")
                for index, item in enumerate(legal_qa_raw, 1):
                    # Jika berupa list of dict
                    if isinstance(item, dict):
                        q = item.get("question", "Pertanyaan")
                        a = item.get("answer", "Jawaban")
                        st.markdown(f"**Q: {q}**\n\n*A: {a}*")
                        st.divider()
                    # Jika berupa list of string murni
                    else:
                        st.info(f"**Langkah {index}:** {item}")
            elif isinstance(legal_qa_raw, str):
                st.markdown(legal_qa_raw)
            else:
                st.warning("Tidak ada data rekomendasi hukum untuk kasus ini.")

        # --- TAB 5: REFERENCES ---
        with tab4:
            st.write("### 📂 Referensi Pasal Konstitusi (Qdrant)")
            retrieved_preview = data.get(
                "retrieved_context_preview") or data.get("retrieved_context")
            if retrieved_preview:
                st.write(f"**Query Pencarian:** `{data.get('search_query')}`")
                st.markdown(retrieved_preview)
            else:
                st.warning("Tidak ada lampiran pasal spesifik.")

        # --- TAB 6: TRANSCRIPTION ---
        with tab5:
            st.write("### 🗣️ Transkripsi Audio")
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                st.info(
                    f"**🗣️ Hasil Transkripsi Suara (Raw):**\n\n{data.get('raw_transcribe')}")
            with col_t2:
                st.success(
                    f"**✨ Hasil Perbaikan Teks (Repaired):**\n\n{data.get('repaired_text')}")

            # Additional metadata
            st.divider()
            st.markdown("#### 🔍 Query Pencarian")
            st.code(data.get('search_query') or '-', language='text')

        # --- TAB 7: RAW LOG ---
        with tab6:
            st.write("### ⚙️ Raw Metadata & JSONB Response")
            with st.expander("Lihat Raw JSON Payload"):
                st.json(data)

    else:
        st.error("Gagal memuat detail riwayat dari database Postgres.")
else:
    st.info("Silakan pilih riwayat analisis terlebih dahulu di sidebar atau lakukan generate data baru.")
