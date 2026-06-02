"""
streamlit_app/components/audio_controls.py  (updated)

Perubahan dari versi lama:
- Tambah tombol "Proses RAG & Evaluasi" yang memanggil integration pipeline
- Tampilkan hasil material SPK hukum setelah pipeline selesai
- Jalankan evaluasi RAGAS otomatis setelah material diterima
- Tampilkan RAGAS strip kecil di bawah material
- Simpan semua hasil ke session_state agar Tab Evaluasi bisa auto-populate
"""

import streamlit as st
import requests
from streamlit_mic_recorder import mic_recorder
# Tambah di bagian import atas
from api.knowledge.knowledge_api import get_knowledgebase_list

from utils.session import (
    get_current_session,
    set_pending_audio_text,
    set_last_rag_result,
    set_last_ragas_result,
    get_last_rag_result,
    get_last_ragas_result,
    get_rag_session_id,
    set_rag_session_id,
    set_ragas_evaluating,
    is_ragas_evaluating,
)

from api.evaluasi.evaluation_api import run_ragas_evaluation
from config.settings import settings
from api.prompting.integration_api import process_audio_integrated, convert_material_to_text


BASE_URL = settings.API_BASE_URL

# ── Session State Keys ────────────────────────────────────────────────────────
_KEY_UPLOAD_BYTES  = "_audio_upload_bytes"
_KEY_UPLOAD_NAME   = "_audio_upload_name"
_KEY_RECORD_BYTES  = "_audio_record_bytes"
_KEY_TRANSCRIPTION = "_audio_transcription"


# ── Helper: transkripsi saja (endpoint lama, tetap dipakai) ───────────────────
def _transcribe(audio_bytes: bytes, filename: str, provider: str) -> tuple[str | None, str | None]:
    try:
        response = requests.post(
            f"{BASE_URL}/prompting/audio/process",
            files={"file": (filename, audio_bytes)},
            data={"provider": provider},
            timeout=60,
        )
        data = response.json()
        if response.status_code != 200:
            detail = data.get("detail", data.get("error", response.text))
            return None, f"Server error {response.status_code}: {detail}"
        if "error" in data:
            return None, data["error"]
        return data.get("transcription", ""), None
    except requests.exceptions.ConnectionError:
        return None, "Tidak dapat terhubung ke server. Pastikan backend berjalan."
    except requests.exceptions.Timeout:
        return None, "Request timeout. Coba file yang lebih pendek."
    except Exception as e:
        return None, str(e)

# ── Helper: warna skor RAGAS ──────────────────────────────────────────────────
def _score_color(score: float | None) -> str:
    if score is None:
        return "gray"
    if score >= 0.8:
        return "green"
    if score >= 0.6:
        return "orange"
    return "red"


def _score_emoji(score: float | None) -> str:
    if score is None:
        return "⬜"
    if score >= 0.8:
        return "🟢"
    if score >= 0.6:
        return "🟡"
    return "🔴"


# ── Helper: render RAGAS strip di bawah material ──────────────────────────────
def _render_ragas_strip(ragas_result: dict):
    """Strip kecil 2–3 metrik utama di bawah hasil material."""
    if not ragas_result or ragas_result.get("status") == "error":
        st.warning(
            f"⚠️ Evaluasi RAGAS gagal: {ragas_result.get('error', 'Unknown error')}",
        )
        return

    metrics = ragas_result.get("metrics", {})
    if not metrics:
        return

    faith = metrics.get("faithfulness")
    relev = metrics.get("answer_relevancy")
    overall = metrics.get("overall_score")
    ts = ragas_result.get("timestamp", "")

    st.markdown(
        f"""
        <div style="
            background: rgba(0,0,0,0.03);
            border: 0.5px solid rgba(0,0,0,0.1);
            border-radius: 8px;
            padding: 8px 14px;
            margin-top: 8px;
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 8px;
            font-size: 12px;
        ">
            <span style="color: #888; margin-right: 4px;">📊 Kualitas RAG:</span>
            <span style="
                background: {'rgba(40,167,69,0.12)' if faith and faith >= 0.8 else 'rgba(253,126,20,0.12)' if faith and faith >= 0.6 else 'rgba(220,53,69,0.12)'};
                color: {'#1a7a35' if faith and faith >= 0.8 else '#b35c00' if faith and faith >= 0.6 else '#a01020'};
                padding: 2px 8px; border-radius: 4px; font-weight: 500;
            ">{_score_emoji(faith)} Faithfulness {f'{faith:.2f}' if faith is not None else 'N/A'}</span>
            <span style="
                background: {'rgba(40,167,69,0.12)' if relev and relev >= 0.8 else 'rgba(253,126,20,0.12)' if relev and relev >= 0.6 else 'rgba(220,53,69,0.12)'};
                color: {'#1a7a35' if relev and relev >= 0.8 else '#b35c00' if relev and relev >= 0.6 else '#a01020'};
                padding: 2px 8px; border-radius: 4px; font-weight: 500;
            ">{_score_emoji(relev)} Relevancy {f'{relev:.2f}' if relev is not None else 'N/A'}</span>
            <span style="
                background: {'rgba(40,167,69,0.12)' if overall and overall >= 0.8 else 'rgba(253,126,20,0.12)' if overall and overall >= 0.6 else 'rgba(220,53,69,0.12)'};
                color: {'#1a7a35' if overall and overall >= 0.8 else '#b35c00' if overall and overall >= 0.6 else '#a01020'};
                padding: 2px 8px; border-radius: 4px; font-weight: 500;
            ">{_score_emoji(overall)} Overall {f'{overall:.2f}' if overall is not None else 'N/A'}</span>
            <span style="color: #aaa; margin-left: auto; font-size: 11px;">
                Lihat detail lengkap di tab Evaluasi · {ts}
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Helper: render hasil material SPK ────────────────────────────────────────
def _render_material_result(material: dict, rag_info: dict):
    """Tampilkan hasil MaterialResponse (format baru) dari pipeline RAG."""
    st.markdown("---")
    st.markdown("### 📋 Hasil Analisis Hukum")

    sources_count = rag_info.get("sources_count", 0)
    has_context   = rag_info.get("has_context", False)
    query_used    = rag_info.get("query_used", "")

    col_a, col_b = st.columns(2)
    with col_a:
        st.caption(f"🔍 Query: *{query_used}*")
    with col_b:
        st.caption(f"📚 Sumber ditemukan: {sources_count} chunk")

    if not has_context or not material:
        st.warning("⚠️ Tidak ditemukan referensi hukum yang relevan.")
        return

    summary = material.get("summary", {}) or {}
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

    legal_qa = material.get("legal_qa", [])
    if legal_qa:
        st.markdown("#### ❓ Legal Q&A")
        for qa in legal_qa:
            with st.expander(f"Q: {qa.get('question', '')}", expanded=True):
                st.write(qa.get("answer", "-"))

    risk = material.get("risk_review", {}) or {}
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

    timeline = material.get("timeline_extraction", [])
    if timeline:
        with st.expander("🕐 Timeline Hukum"):
            for item in timeline:
                st.markdown(
                    f"- **{item.get('date_or_period', '')}** — "
                    f"{item.get('event', '')} "
                    f"*(Ref: {item.get('article_reference', '-')})*"
                )

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

    referensi = material.get("referensi_uu", [])
    if referensi:
        with st.expander("📚 Referensi Undang-Undang"):
            for ref in referensi:
                st.markdown(
                    f"- **{ref.get('source_name', '')}** Pasal {ref.get('article', '')}"
                )


# ── MAIN RENDER ───────────────────────────────────────────────────────────────
def render_audio_controls():

    st.divider()
    st.subheader("🎙️ Audio ke Analisis Hukum")
    st.caption("Upload atau rekam audio — sistem akan mentranskrip, mencari referensi hukum, dan menghasilkan analisis SPK otomatis.")

    # ── Provider STT ──────────────────────────────────────────────────────────
    provider = st.selectbox(
        "Provider STT:",
        ["whisper", "elevenlabs"],
        help="Whisper (Groq) — cepat & gratis. ElevenLabs — akurasi tinggi.",
    )

    # ── Knowledge Base ────────────────────────────────────────────────────────
    st.session_state["kb_list"] = get_knowledgebase_list()
    kb_list = st.session_state["kb_list"]

    kb_list = get_knowledgebase_list()

    knowledge_base = st.selectbox(
        "Knowledge Base:",
        options=kb_list if kb_list else [],
        index=0 if kb_list else None,
        placeholder="Tidak ada KB tersedia" if not kb_list else None,
        help="Pilih collection Qdrant yang relevan.",
    )

    if st.button("🔄 Refresh Knowledge Base", key="btn_refresh_kb"):
        st.session_state["kb_list"] = get_knowledgebase_list()
        st.rerun()

    # Tab upload / record
    tab_upload, tab_record = st.tabs(["📂 Upload File", "🔴 Rekam Langsung"])

    # ── TAB UPLOAD ────────────────────────────────────────────────────────────
    with tab_upload:
        uploaded_audio = st.file_uploader(
            "Pilih file audio",
            type=["mp3", "wav", "m4a", "ogg", "webm"],
            label_visibility="collapsed",
            key="audio_file_uploader",
        )

        if uploaded_audio is not None:
            st.session_state[_KEY_UPLOAD_BYTES] = uploaded_audio.read()
            st.session_state[_KEY_UPLOAD_NAME] = uploaded_audio.name

        upload_bytes = st.session_state.get(_KEY_UPLOAD_BYTES)
        upload_name = st.session_state.get(_KEY_UPLOAD_NAME, "audio.wav")

        if upload_bytes:
            st.audio(upload_bytes)

            col_rag, col_stt, col_clear = st.columns([3, 2, 1])

            with col_rag:
                # Tombol utama — pipeline RAG lengkap + evaluasi
                process_rag = st.button(
                    "🚀 Proses RAG & Evaluasi",
                    use_container_width=True,
                    key="btn_rag_upload",
                    type="primary",
                    help="STT → RAG → Generate Material → Evaluasi RAGAS otomatis",
                )

            with col_stt:
                # Tombol lama — hanya transkripsi
                transcribe_only = st.button(
                    "📝 Transkripsi Saja",
                    use_container_width=True,
                    key="btn_transcribe_upload",
                )

            with col_clear:
                if st.button("🗑️", use_container_width=True, key="btn_clear_upload"):
                    st.session_state.pop(_KEY_UPLOAD_BYTES, None)
                    st.session_state.pop(_KEY_UPLOAD_NAME, None)
                    st.session_state.pop(_KEY_TRANSCRIPTION, None)
                    st.rerun()

            # ── Proses RAG lengkap ─────────────────────────────────────────
            if process_rag:
                _run_rag_pipeline(upload_bytes, upload_name, provider, knowledge_base)

            # ── Transkripsi saja (flow lama) ───────────────────────────────
            if transcribe_only:
                st.session_state.pop(_KEY_TRANSCRIPTION, None)
                with st.spinner("Sedang memproses transkripsi..."):
                    transcription, error = _transcribe(upload_bytes, upload_name, provider)
                if error:
                    st.error(f"⚠️ {error}")
                else:
                    st.session_state[_KEY_TRANSCRIPTION] = transcription
                    st.rerun()

    # ── TAB RECORD ────────────────────────────────────────────────────────────
    with tab_record:
        st.caption("Klik **Start** untuk mulai merekam, **Stop** untuk menyelesaikan.")

        audio_data = mic_recorder(
            start_prompt="🔴 Start Rekam",
            stop_prompt="⏹️ Stop Rekam",
            just_once=True,
            use_container_width=True,
            key="mic_recorder",
        )

        if audio_data and audio_data.get("bytes"):
            st.session_state[_KEY_RECORD_BYTES] = audio_data["bytes"]
            st.session_state.pop(_KEY_TRANSCRIPTION, None)

        record_bytes = st.session_state.get(_KEY_RECORD_BYTES)

        if record_bytes:
            st.audio(record_bytes, format="audio/wav")

            col_rag, col_stt, col_clear = st.columns([3, 2, 1])

            with col_rag:
                process_rag_rec = st.button(
                    "🚀 Proses RAG & Evaluasi",
                    use_container_width=True,
                    key="btn_rag_record",
                    type="primary",
                )

            with col_stt:
                transcribe_record = st.button(
                    "📝 Transkripsi Saja",
                    use_container_width=True,
                    key="btn_transcribe_record",
                )

            with col_clear:
                if st.button("🗑️", use_container_width=True, key="btn_clear_record"):
                    st.session_state.pop(_KEY_RECORD_BYTES, None)
                    st.session_state.pop(_KEY_TRANSCRIPTION, None)
                    st.rerun()

            if process_rag_rec:
                _run_rag_pipeline(record_bytes, "recording.wav", provider, knowledge_base)

            if transcribe_record:
                st.session_state.pop(_KEY_TRANSCRIPTION, None)
                with st.spinner("Sedang memproses transkripsi rekaman..."):
                    transcription, error = _transcribe(record_bytes, "recording.wav", provider)
                if error:
                    st.error(f"⚠️ {error}")
                else:
                    st.session_state[_KEY_TRANSCRIPTION] = transcription
                    st.rerun()

    # ── Hasil transkripsi saja (flow lama, tidak berubah) ─────────────────────
    transcription = st.session_state.get(_KEY_TRANSCRIPTION)
    if transcription is not None:
        _handle_transcription_success(transcription)

    # ── Tampilkan hasil RAG + RAGAS strip (jika ada) ──────────────────────────
    rag_result = get_last_rag_result()
    if rag_result:
        _render_material_result(
            material=rag_result.get("generated_material"),
            rag_info={"has_context": rag_result.get("has_context", False),
                      "sources_count": rag_result.get("sources_count", 0), 
                      "query_used": rag_result.get("query_used", "")
                    },
        )

        # RAGAS strip
        ragas_result = get_last_ragas_result()
        if is_ragas_evaluating():
            st.info("⏳ Evaluasi RAGAS sedang berjalan...")
        elif ragas_result:
            _render_ragas_strip(ragas_result)

        st.caption(
            "💡 Lihat **Tab Evaluasi** untuk detail lengkap 4 metrik + tambah ground truth."
        )


# ── CORE: pipeline RAG + RAGAS otomatis ──────────────────────────────────────
def _run_rag_pipeline(
    audio_bytes: bytes,
    filename: str,
    provider: str,
    knowledge_base: str,
):
    print(f"[RAG DEBUG] knowledge_base dikirim: '{knowledge_base}'")

    # Step 1: RAG pipeline
    with st.spinner("⏳ Memproses audio → RAG → Material... (30–90 detik)"):
        rag_response = process_audio_integrated(
            audio_bytes=audio_bytes,
            filename=filename,
            provider=provider,
            knowledge_base=knowledge_base,
            auto_evaluate=False,
            session_id=get_rag_session_id(),
        )

    if rag_response["status"] == "error":
        st.error(f"❌ Pipeline RAG gagal: {rag_response['error']}")
        return

    transcription = rag_response.get("transcription", {})
    material      = rag_response.get("generated_material")
    context       = rag_response.get("raw_context", "")
    rag_meta      = rag_response.get("rag", {})
    question      = transcription.get("repaired", transcription.get("raw", ""))

    # Konversi material ke teks via backend — frontend tidak tahu format internal
    answer_text = ""
    if material:
        with st.spinner("🔄 Menyiapkan data evaluasi..."):
            answer_text = convert_material_to_text(material)

    print(f"[DEBUG] context length: {len(context)}")
    print(f"[DEBUG] answer_text length: {len(answer_text)}")

    # Step 2: Simpan hasil RAG ke session_state
    set_last_rag_result(
        question=question,
        context=context,
        answer_text=answer_text,
        generated_material=material,
        transcription_raw=transcription.get("raw", ""),
        knowledge_base=knowledge_base,
        sources_count=rag_meta.get("sources_count", 0),
        has_context=rag_meta.get("has_context", False),
        query_used=rag_meta.get("query_used", question),
        history_id=rag_response.get("history_id"),
        session_id=rag_response.get("session_id"),
    )
    set_rag_session_id(rag_response.get("session_id") or get_rag_session_id())

    # Step 3: Evaluasi RAGAS — hanya jika kedua input tersedia
    if context and answer_text:
        set_ragas_evaluating(True)
        with st.spinner("📊 Mengevaluasi kualitas RAG dengan RAGAS..."):
            ragas_response = run_ragas_evaluation(
                question=question,
                context=context,
                answer=answer_text,
                ground_truth=None,
            )
        set_last_ragas_result(ragas_response)
        set_ragas_evaluating(False) 
    else:
        st.warning(
            "⚠️ Evaluasi RAGAS dilewati — "
            + ("context kosong. " if not context else "")
            + ("answer_text kosong." if not answer_text else "")
        )
        set_ragas_evaluating(False)

    st.session_state["_force_refresh_history"] = True
    # ✅ Invalidate sidebar history cache agar fetch ulang dari DB
    st.session_state.pop("_db_history_cache", None)  # double safety

    st.rerun()


# ── HELPER: transkripsi berhasil (flow lama, tidak berubah) ──────────────────
def _handle_transcription_success(transcription: str):
    st.success("✅ Transkripsi berhasil!")

    st.text_area(
        "Hasil Transkripsi:",
        value=transcription,
        height=150,
        key="transcription_preview",
    )

    col_send, col_copy = st.columns(2)

    with col_send:
        if st.button("💬 Kirim ke Chat", use_container_width=True, key="btn_send_to_chat"):
            current_session = get_current_session()
            if current_session is None:
                st.warning("Buat chat baru terlebih dahulu.")
            else:
                set_pending_audio_text(transcription)
                st.session_state.pop(_KEY_TRANSCRIPTION, None)
                st.info("✅ Teks dikirim ke chat input.")
                st.rerun()

    with col_copy:
        st.code(transcription, language=None)