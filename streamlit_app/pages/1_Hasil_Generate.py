# streamlit_app/pages/1_Hasil_Generate.py

# pyrefly: ignore [missing-import]
import streamlit as st
import json  # 🛠️ Tambahkan import ini untuk membongkar string JSON
from api.history.history_api import get_history_by_id, get_all_history
from api.evaluasi.evaluation_api import run_ragas_evaluation, run_ragas_reeval
from components.left_sidebar import render_left_sidebar
from utils.session import init_session_state
from components.evaluation_ui import render_evaluation_section

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

        # Cek apakah material berisi info no_context atau retrieved_context kosong
        material_info = material.get("_info") if isinstance(material, dict) else None
        is_no_context = (
            material_info == "no_context" 
            or data.get("data_status") == "no_context"
            or not data.get("retrieved_context")
            or len(data.get("retrieved_context").strip()) == 0
        )
        no_context_message = material.get("message") if isinstance(material, dict) else None
        if not no_context_message:
            no_context_message = data.get("data_message") or (
                "Referensi hukum yang Anda cari belum tersedia di Knowledge Base saat ini. "
                "Silakan tambahkan knowledge base yang relevan terlebih dahulu "
                "melalui fitur insert knowledge base agar sistem dapat memberikan "
                "analisis yang akurat dan benar."
            )

        # =========================================
        # KOMPONEN 5 TABS UTAMA (Raw Log dihapus)
        # =========================================
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📝 Ringkasan", "⚠️ Potensi Penyimpangan", "❓ Tanya Jawab",
            "📂 Sumber Pasal", "🗣️ Transkripsi"
        ])

        # --- PESAN NO CONTEXT (ditampilkan di semua tab jika tidak ada referensi) ---
        no_context_html = f"""
        <div style="
            background: rgba(255, 193, 7, 0.08);
            border: 1px solid rgba(255, 193, 7, 0.25);
            border-radius: 10px;
            padding: 24px 20px;
            text-align: center;
            margin: 20px 0;
        ">
            <div style="font-size: 36px; margin-bottom: 12px;">📚</div>
            <div style="font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px;">
                Referensi Hukum Belum Tersedia
            </div>
            <div style="font-size: 13.5px; color: var(--text-secondary); line-height: 1.7; max-width: 600px; margin: 0 auto;">
                {no_context_message}
            </div>
        </div>
        """

        # --- TAB 1: SUMMARY ---
        with tab1:
            st.write("### 📝 Ringkasan Analisis Pasal")
            if is_no_context:
                st.warning("⚠️ Tidak bisa generate ringkasan karena pembahasan tentang ini tidak ditemukan di database. Silakan pilih database knowledgebase yang sesuai, dan berikan prompt dengan menyebutkan pasal atau pertanyaan yang menyerupai bunyi ayatnya agar proses generate berhasil.")
            else:
                if "dasar_hukum" in material or "ringkasan" in material:
                    # Render new structure
                    ringkasan_pembuka = material.get("ringkasan_pembuka")
                    if ringkasan_pembuka and ringkasan_pembuka != "-":
                        st.markdown(ringkasan_pembuka)

                    st.markdown("#### **Poin-Poin Penting:**")
                    ringkasan_list = material.get("ringkasan") or []
                    if ringkasan_list:
                        for item in ringkasan_list:
                            poin = item.get("poin") if isinstance(item, dict) else str(item)
                            st.markdown(f"- {poin}")
                    else:
                        st.markdown("*- Tidak ada poin ringkasan.*")

                    st.divider()
                    st.markdown("#### **Identifikasi Dasar Hukum:**")
                    dasar_hukum_list = material.get("dasar_hukum") or []
                    if dasar_hukum_list:
                        for idx, item in enumerate(dasar_hukum_list, 1):
                            if isinstance(item, dict):
                                peraturan = item.get("nama_peraturan") or ""
                                pasal = item.get("pasal") or ""
                                ayat = item.get("ayat") or "-"
                                catatan = item.get("catatan_validasi") or "-"
                                
                                label_ayat = f", {ayat}" if ayat and ayat != "-" else ""
                                st.markdown(f"**{idx}. {peraturan} {pasal}{label_ayat}**")
                                if catatan and catatan != "-":
                                    st.info(f"💡 **Catatan Validasi/Koreksi:** {catatan}")
                    else:
                        st.markdown("*- Tidak ada dasar hukum yang teridentifikasi.*")

                    konteks_tambahan = material.get("konteks_tambahan")
                    if konteks_tambahan and konteks_tambahan != "-":
                        st.divider()
                        st.markdown(f"#### **Konteks Tambahan:**\n{konteks_tambahan}")
                else:
                    # Render old structure
                    summary_raw = material.get("summary")

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
            st.write("### ⚠️ Potensi Penyimpangan Terhadap Pasal")
            if is_no_context:
                st.warning("⚠️ Tidak bisa generate risiko karena tidak ditemukan referensi di database. Silakan pilih database knowledgebase yang sesuai, dan berikan prompt dengan menyebutkan pasal atau pertanyaan yang menyerupai bunyi ayatnya agar proses generate berhasil.")
            else:
                if "analisa_risiko" in material:
                    st.caption(
                        "Contoh kondisi yang TIDAK SESUAI dengan ketentuan pasal di atas — "
                        "ilustrasi edukatif umum, bukan penilaian terhadap tindakan Anda secara spesifik."
                    )
                    risiko_list = material.get("analisa_risiko") or []
                    if risiko_list:
                        for idx, item in enumerate(risiko_list, 1):
                            if isinstance(item, dict):
                                skenario = item.get("skenario") or ""
                                penjelasan = item.get("penjelasan") or ""
                                st.warning(f"**Contoh Penyimpangan #{idx}:**\n{skenario}")
                                st.markdown(f"**Penjelasan:**\n{penjelasan}")
                                st.divider()
                    else:
                        st.success("✅ Tidak ditemukan contoh penyimpangan yang relevan untuk pasal ini.")
                else:
                    # Render old structure
                    risk_raw = material.get("risk_review")

                    if isinstance(risk_raw, str):
                        risk_raw = risk_raw.strip()
                        if risk_raw.startswith("{"):
                            try:
                                risk_raw = json.loads(risk_raw)
                            except:
                                pass

                    if isinstance(risk_raw, dict):
                        col_r1, col_r2 = st.columns(2)
                        with col_r1:
                            status_risiko = risk_raw.get("status", "N/A")
                            st.metric(label="Status Risiko", value=status_risiko)
                        with col_r2:
                            skor_risiko = risk_raw.get("score", 0)
                            st.metric(label="Skor Tingkat Risiko",
                                      value=f"{skor_risiko}/100")

                        st.divider()

                        if risk_raw.get("analysis"):
                            st.markdown(
                                f"#### 🔍 Analisis Mendalam:\n{risk_raw.get('analysis')}")

                        risks_list = risk_raw.get("risks", [])
                        if risks_list:
                            st.markdown("#### 🚨 Daftar Bahaya Risiko yang Terdeteksi:")
                            for idx, rsk in enumerate(risks_list, 1):
                                rsk_clean = str(rsk).replace(
                                    '[', '').replace(']', '').replace('"', '')
                                st.error(f"**{idx}.** {rsk_clean}")

                        if risk_raw.get("recommendation"):
                            st.warning(
                                f"💡 **Rekomendasi Utama:** {risk_raw.get('recommendation')}")

                        mitigasi_list = risk_raw.get("mitigation_steps", [])
                        if mitigasi_list:
                            st.markdown("#### 🛡️ Langkah Mitigasi / Pencegahan:")
                            for idx, mit in enumerate(mitigasi_list, 1):
                                mit_clean = str(mit).replace(
                                    '[', '').replace(']', '').replace('"', '')
                                st.info(f"**Langkah {idx}:** {mit_clean}")

                    elif isinstance(risk_raw, list):
                        for index, risk in enumerate(risk_raw, 1):
                            risk_str = str(risk).replace("[", "").replace(
                                "]", "").replace('"', '').replace("'", "")
                            if risk_str.strip():
                                st.error(f"**Risiko #{index}:** {risk_str}")
                    else:
                        st.warning(
                            "Data analisis risiko kosong atau tidak kompatibel dengan format sistem.")

        # --- TAB 3: LEGAL QA ---
        with tab3:
            st.write("### ❓ Tanya Jawab Seputar Pasal")
            if is_no_context:
                st.warning("⚠️ Tidak bisa generate tanya jawab karena tidak ditemukan referensi di database. Silakan pilih database knowledgebase yang sesuai, dan berikan prompt dengan menyebutkan pasal atau pertanyaan yang menyerupai bunyi ayatnya agar proses generate berhasil.")
            else:
                if "qa" in material:
                    st.caption("Pertanyaan yang mungkin muncul dari pembaca terkait pasal ini, beserta jawabannya.")
                    qa_list = material.get("qa") or []
                    if qa_list:
                        for index, item in enumerate(qa_list, 1):
                            if isinstance(item, dict):
                                q = item.get("pertanyaan", "Pertanyaan")
                                a = item.get("jawaban", "Jawaban")
                                st.markdown(f"**Q: {q}**\n\n*A: {a}*")
                                st.divider()
                    else:
                        st.warning("Tidak ada data tanya-jawab hukum untuk kasus ini.")
                else:
                    # Render old structure
                    legal_qa_raw = material.get("legal_qa")

                    if isinstance(legal_qa_raw, str) and legal_qa_raw.strip().startswith("["):
                        try:
                            legal_qa_raw = json.loads(legal_qa_raw)
                        except:
                            pass

                    if isinstance(legal_qa_raw, list):
                        st.markdown("#### 💡 Langkah/Saran Strategis Hukum:")
                        for index, item in enumerate(legal_qa_raw, 1):
                            if isinstance(item, dict):
                                q = item.get("question", "Pertanyaan")
                                a = item.get("answer", "Jawaban")
                                st.markdown(f"**Q: {q}**\n\n*A: {a}*")
                                st.divider()
                            else:
                                st.info(f"**Langkah {index}:** {item}")
                    elif isinstance(legal_qa_raw, str):
                        st.markdown(legal_qa_raw)
                    else:
                        st.warning("Tidak ada data rekomendasi hukum untuk kasus ini.")

        # --- TAB 4: REFERENCES ---
        with tab4:
            st.write("### 📂 Sumber Pasal yang Digunakan")
            if is_no_context:
                st.warning("⚠️ Tidak bisa melampirkan pasal karena tidak ditemukan di database. Silakan pilih database knowledgebase yang sesuai, dan berikan prompt dengan menyebutkan pasal atau pertanyaan yang menyerupai bunyi ayatnya agar proses generate berhasil.")
            else:
                retrieved_preview = data.get(
                    "retrieved_context_preview") or data.get("retrieved_context")
                if retrieved_preview:
                    st.write(f"**Query Pencarian:** `{data.get('search_query')}`")
                    st.markdown(retrieved_preview)
                else:
                    st.warning("Tidak ada lampiran pasal spesifik.")

        # --- TAB 5: TRANSCRIPTION ---
        with tab5:
            st.write("### 🗣️ Transkripsi Audio")
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                st.info(
                    f"**🗣️ Hasil Transkripsi Suara (Raw):**\n\n{data.get('raw_transcribe')}")
            with col_t2:
                st.success(
                    f"**✨ Hasil Perbaikan Teks (Repaired):**\n\n{data.get('repaired_text')}")

            st.divider()
            st.markdown("#### 🔍 Query Pencarian")
            st.code(data.get('search_query') or '-', language='text')

        
        render_evaluation_section(data=data, session_id=session_id)

    else:
        st.error("Gagal memuat detail riwayat dari database Postgres.")
else:
    st.info("Silakan pilih riwayat analisis terlebih dahulu di sidebar atau lakukan generate data baru.")
