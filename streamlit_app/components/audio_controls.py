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
    set_ragas_evaluating,
    is_ragas_evaluating,
)
from api.prompting.integration_api import process_audio_integrated
from api.evaluasi.evaluation_api import run_ragas_evaluation
from config.settings import settings

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


# ── Helper: format material SPK ke teks plain (untuk RAGAS) ──────────────────
def _material_to_text(material: dict) -> str:
    if not material:
        return ""
    parts = []
    if material.get("decision_status"):
        parts.append(f"Status Keputusan: {material['decision_status']}")
    if material.get("compliance_score") is not None:
        parts.append(f"Skor Kepatuhan: {material['compliance_score']}")
    if material.get("recommendation"):
        parts.append(f"Rekomendasi: {material['recommendation']}")
    if material.get("risk_analysis"):
        parts.append(f"Analisis Risiko: {' | '.join(material['risk_analysis'])}")
    if material.get("legal_basis"):
        parts.append(f"Dasar Hukum: {' | '.join(material['legal_basis'])}")
    return "\n\n".join(parts)


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
                    "🚀 Proses RAG",
                    use_container_width=True,
                    key="btn_rag_upload",
                    type="primary",
                    help="STT → RAG → Generate Material → Evaluasi RAGAS otomatis",
                )

            # ── Proses RAG lengkap ─────────────────────────────────────────
            if process_rag:
                _run_rag_pipeline(upload_bytes, upload_name, provider, knowledge_base)

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
                    "🚀 Proses RAG",
                    use_container_width=True,
                    key="btn_rag_record",
                    type="primary",
                )


            if process_rag_rec:
                _run_rag_pipeline(record_bytes, "recording.wav", provider, knowledge_base)


    # ── Hasil transkripsi saja (flow lama, tidak berubah) ─────────────────────
    transcription = st.session_state.get(_KEY_TRANSCRIPTION)
    if transcription is not None:
        _handle_transcription_success(transcription)

# ── Tampilkan hasil RAG + RAGAS strip (jika ada) ──────────────────────────
    rag_result = get_last_rag_result()
    if rag_result:
        # Jika evaluasi RAGAS background masih jalan, beri info tipis
        ragas_result = get_last_ragas_result()
        if is_ragas_evaluating():
            st.info("⏳ Evaluasi RAGAS sedang berjalan...")
        elif ragas_result:
            _render_ragas_strip(ragas_result)

        st.caption(
            f"💡 Analisis selesai. Lihat detail lengkap di **Halaman Hasil Generate**."
        )


# ── CORE: pipeline RAG + RAGAS otomatis ──────────────────────────────────────
def _run_rag_pipeline(
    audio_bytes: bytes,
    filename: str,
    provider: str,
    knowledge_base: str,
):
    print(f"[RAG DEBUG] knowledge_base dikirim: '{knowledge_base}'")
    
    # ── Step 1: Jalankan RAG Pipeline ─────────────────────────────────────────
    with st.spinner("⏳ Memproses audio → RAG → Material... (30–90 detik)"):
        rag_response = process_audio_integrated(
            audio_bytes=audio_bytes,
            filename=filename,
            provider=provider,
            knowledge_base=knowledge_base,
        )

    if rag_response["status"] == "error":
        st.error(f"❌ Pipeline RAG gagal: {rag_response['error']}")
        return

    transcription   = rag_response.get("transcription", {})
    material        = rag_response.get("generated_material")
    context         = rag_response.get("raw_context", "")
    fallback_message = rag_response.get("fallback_message")

    if rag_response["status"] == "failed" and fallback_message:
        st.warning(f"⚠️ Tidak bisa menghasilkan material: {fallback_message}")
    rag_meta        = rag_response.get("rag", {})
    question        = transcription.get("repaired", transcription.get("raw", ""))
    answer_text     = _material_to_text(material) if material else ""

    new_session_id = rag_response.get("session_id") or rag_response.get("id")

    # Debug log
    print(f"[DEBUG] has_context: {rag_meta.get('has_context')}")
    print(f"[DEBUG] sources_count: {rag_meta.get('sources_count')}")
    print(f"[DEBUG] context length: {len(context)}")
    print(f"[DEBUG] material: {material}")
    print(f"[DEBUG] new_session_id didapat: {new_session_id}")

    # ── Step 2: Simpan hasil RAG ke session_state ─────────────────────────────
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
    )

    # ── Step 3 & 4: Evaluasi RAGAS (jika ada context dan material) ─────────────
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
    else:
        set_ragas_evaluating(False)

# ── Step 5: Auto Redirect ke Halaman Riwayat Baru ─────────────────────────
    if new_session_id:
        # Masukkan ID ke session state global agar bisa dibaca oleh halaman Hasil_Generate
        st.session_state["current_session_id"] = new_session_id
        
        st.toast("🚀 Analisis Selesai! Mengalihkan ke dashboard...")
        
        # Pindah ke file 1_Hasil_Generate.py
        st.switch_page("pages/1_Hasil_Generate.py")
    else:
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