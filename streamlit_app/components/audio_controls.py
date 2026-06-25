# streamlit_app/components/audio_controls.py
# INPUT-ONLY: handles audio upload/record, transcription, and RAG pipeline trigger.
# After successful generation, redirects to page 1_Hasil_Generate.py.

import logging
from pathlib import Path
import time
import requests
import streamlit as st
from streamlit_mic_recorder import mic_recorder

from api.knowledge.knowledge_api import get_knowledgebase_list
from api.prompting.integration_api import process_audio_integrated, process_text_integrated
from config.settings import settings
from utils.session import (
    set_last_rag_result,
    get_rag_session_id,
    set_rag_session_id,
)

logger = logging.getLogger(__name__)

BASE_URL = settings.API_BASE_URL

_KEY_UPLOAD_BYTES = "_audio_upload_bytes"
_KEY_UPLOAD_NAME = "_audio_upload_name"
_KEY_RECORD_BYTES = "_audio_record_bytes"
_KEY_TRANSCRIPTION = "_audio_transcription"
_KEY_TEXT_INPUT = "_text_input_content"


# =============================================================================
# CSS
# =============================================================================

def _inject_styles():
    css_path = Path(__file__).resolve().parent.parent / \
        "assets" / "styles" / "main.css"
    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

    # CSS + JS to force ALL selectboxes into pure dropdown (no typing / no delete / no search)
    # Uses document-level capture-phase listeners for reliability across re-renders.
    st.markdown(
        """
        <style>
        /* Hide caret and prevent text selection on all selectbox inputs */
        div[data-testid="stSelectbox"] input[role="combobox"] {
            caret-color: transparent !important;
            user-select: none !important;
            -webkit-user-select: none !important;
        }
        </style>
        <script>
        (function() {
            // Use capture-phase on document — fires BEFORE Streamlit's React handlers.
            // Survives re-renders because it's on document, not the element.
            if (window.__stSelectboxLocked) return;
            window.__stSelectboxLocked = true;

            function isSelectboxInput(el) {
                if (!el || !el.getAttribute) return false;
                return el.getAttribute('role') === 'combobox' &&
                       el.closest && el.closest('div[data-testid="stSelectbox"]');
            }

            // Block ALL keyboard input on selectbox combobox inputs
            document.addEventListener('keydown', function(e) {
                if (isSelectboxInput(e.target)) {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                }
            }, true);

            // Block any programmatic input/value changes
            document.addEventListener('input', function(e) {
                if (isSelectboxInput(e.target)) {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                }
            }, true);

            // Block paste
            document.addEventListener('paste', function(e) {
                if (isSelectboxInput(e.target)) {
                    e.preventDefault();
                }
            }, true);
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# HELPERS
# =============================================================================

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
    except Exception as exc:
        return None, str(exc)


# =============================================================================
# MAIN RENDER (input only — no result display)
# =============================================================================

def render_audio_controls():
    _inject_styles()

    st.markdown(
        """
        <div style="margin-top:8px;margin-bottom:4px;">
            <div class="ac-header">🎙️ Analisis Hukum Berbasis AI</div>
            <div class="ac-subheader">
                Upload audio, rekam langsung, atau ketik teks — sistem akan mencari referensi hukum
                dan menghasilkan analisis SPK secara otomatis.
            </div>
        </div>
        <div class="ac-divider"></div>
        """,
        unsafe_allow_html=True,
    )

    col_provider, col_kb = st.columns([1, 2])

    with col_provider:
        st.markdown('<div class="ac-label">Provider STT</div>',
                    unsafe_allow_html=True)
        provider = st.selectbox(
            "Provider STT",
            options=["whisper", "elevenlabs"],
            format_func=lambda x: "🎧 Groq (whisper-large-v3)" if x == "whisper" else "🎙️ ElevenLabs (scribe_v1)",
            label_visibility="collapsed",
            help="Pilih provider STT: Groq Whisper cepat & gratis, ElevenLabs akurasi tinggi.",
        )

    with col_kb:
        st.markdown('<div class="ac-label">Knowledge Base</div>',
                    unsafe_allow_html=True)
        kb_list = get_knowledgebase_list()
        st.session_state["kb_list"] = kb_list

        kb_col, refresh_col = st.columns([4, 1], vertical_alignment="bottom")
        with kb_col:
            knowledge_base = st.selectbox(
                "Knowledge Base",
                options=kb_list if kb_list else [],
                index=0 if kb_list else None,
                placeholder="Tidak ada KB tersedia" if not kb_list else None,
                label_visibility="collapsed",
                help="Pilih collection Qdrant yang relevan.",
            )
        with refresh_col:
            if st.button("🔄", use_container_width=True, key="btn_refresh_kb", help="Refresh KB"):
                st.session_state["kb_list"] = get_knowledgebase_list()
                st.rerun()

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # ── RAGAS Evaluation Toggle ───────────────────────────────────────────────
    auto_eval = st.toggle(
        "📊 Evaluasi RAGAS Otomatis",
        value=False,
        key="toggle_auto_evaluate",
        help="Jika aktif, metrik RAGAS (Faithfulness, Answer Relevancy, Context Precision/Recall) akan dihitung otomatis di background setelah generate.",
    )

    st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

    tab_upload, tab_record, tab_text = st.tabs(
        ["  📂  Upload File  ", "  🔴  Rekam Langsung  ", "  ✏️  Input Teks  "])

    # Dynamic button label based on toggle state
    _rag_btn_label = "🚀  Proses RAG & Evaluasi" if auto_eval else "🚀  Proses RAG"

    # ── TAB UPLOAD ────────────────────────────────────────────────────────────
    with tab_upload:
        st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

        # Only show uploader if no file is loaded yet (enforce 1 file only)
        _has_upload = st.session_state.get(_KEY_UPLOAD_BYTES) is not None

        if not _has_upload:
            uploaded_audio = st.file_uploader(
                "Seret & lepas file audio di sini, atau klik untuk memilih",
                type=["mp3", "wav", "m4a", "ogg", "webm"],
                key="audio_file_uploader",
                help="Maksimal 5 MB. Hanya 1 file audio. Format: MP3, WAV, M4A, OGG, WEBM.",
            )
            if uploaded_audio is not None:
                # Client-side size check (5 MB max, matches backend stt_service.MAX_FILE_SIZE)
                _file_bytes = uploaded_audio.getvalue()
                _size_mb = len(_file_bytes) / (1024 * 1024)
                if _size_mb > 5:
                    st.error(
                        f"⚠️ File terlalu besar ({_size_mb:.1f} MB). Maksimal 5 MB.")
                else:
                    st.session_state[_KEY_UPLOAD_BYTES] = _file_bytes
                    st.session_state[_KEY_UPLOAD_NAME] = uploaded_audio.name
                    st.rerun()

        upload_bytes = st.session_state.get(_KEY_UPLOAD_BYTES)
        upload_name = st.session_state.get(_KEY_UPLOAD_NAME, "audio.wav")

        if upload_bytes:
            st.audio(upload_bytes)
            col_rag, col_stt, col_clear = st.columns([3, 2, 1])
            with col_rag:
                process_rag = st.button(
                    _rag_btn_label, use_container_width=True,
                    key="btn_rag_upload", type="primary",
                    help="STT → RAG → Generate Material → Redirect ke halaman hasil",
                )
            with col_stt:
                transcribe_only = st.button(
                    "📝  Transkripsi Saja", use_container_width=True, key="btn_transcribe_upload",
                )
            with col_clear:
                if st.button("🗑️", use_container_width=True, key="btn_clear_upload", help="Hapus file"):
                    st.session_state.pop(_KEY_UPLOAD_BYTES, None)
                    st.session_state.pop(_KEY_UPLOAD_NAME, None)
                    st.session_state.pop(_KEY_TRANSCRIPTION, None)
                    st.rerun()

            if process_rag:
                _run_rag_pipeline(upload_bytes, upload_name,
                                  provider, knowledge_base, auto_eval)
            if transcribe_only:
                st.session_state.pop(_KEY_TRANSCRIPTION, None)
                with st.spinner("Sedang memproses transkripsi..."):
                    transcription, error = _transcribe(
                        upload_bytes, upload_name, provider)
                if error:
                    st.error(f"⚠️ {error}")
                else:
                    st.session_state[_KEY_TRANSCRIPTION] = transcription
                    st.rerun()

    # ── TAB RECORD ────────────────────────────────────────────────────────────
    with tab_record:
        st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
        st.caption(
            "Klik **Start** untuk mulai merekam, **Stop** untuk menyelesaikan.")

        audio_data = mic_recorder(
            start_prompt="🔴  Start Rekam", stop_prompt="⏹️  Stop Rekam",
            just_once=True, use_container_width=True, key="mic_recorder",
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
                    _rag_btn_label, use_container_width=True,
                    key="btn_rag_record", type="primary",
                )
            with col_stt:
                transcribe_record = st.button(
                    "📝  Transkripsi Saja", use_container_width=True, key="btn_transcribe_record",
                )
            with col_clear:
                if st.button("🗑️", use_container_width=True, key="btn_clear_record", help="Hapus rekaman"):
                    st.session_state.pop(_KEY_RECORD_BYTES, None)
                    st.session_state.pop(_KEY_TRANSCRIPTION, None)
                    st.rerun()

            if process_rag_rec:
                _run_rag_pipeline(record_bytes, "recording.wav",
                                  provider, knowledge_base, auto_eval)
            if transcribe_record:
                st.session_state.pop(_KEY_TRANSCRIPTION, None)
                with st.spinner("Sedang memproses transkripsi rekaman..."):
                    transcription, error = _transcribe(
                        record_bytes, "recording.wav", provider)
                if error:
                    st.error(f"⚠️ {error}")
                else:
                    st.session_state[_KEY_TRANSCRIPTION] = transcription
                    st.rerun()

    # ── TAB TEXT INPUT ─────────────────────────────────────────────────────────
    with tab_text:
        st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
        st.caption(
            "Ketik atau tempel teks pertanyaan/kasus hukum Anda, lalu proses langsung ke pipeline RAG."
        )

        # Ambil nilai tersimpan dari session state (jika ada)
        saved_text = st.session_state.get(_KEY_TEXT_INPUT, "")

        text_content = st.text_area(
            "Teks Pertanyaan",
            value=saved_text,
            height=200,
            placeholder="Contoh: Bagaimana ketentuan pasal 33 UUD 1945 tentang perekonomian nasional?",
            key="text_input_area",
            label_visibility="collapsed",
            help="Masukkan teks pertanyaan atau deskripsi kasus hukum untuk dianalisis.",
        )

        # Update session state jika teks berubah
        if text_content != saved_text:
            st.session_state[_KEY_TEXT_INPUT] = text_content

        # Tombol aksi
        col_process_text, col_clear_text = st.columns([4, 1])
        with col_process_text:
            process_text_btn = st.button(
                _rag_btn_label,
                use_container_width=True,
                key="btn_rag_text",
                type="primary",
                disabled=not text_content.strip(),
                help="Proses teks langsung ke pipeline RAG (Repair → Search → Generate → Save).",
            )
        with col_clear_text:
            if st.button("🗑️", use_container_width=True, key="btn_clear_text", help="Hapus teks"):
                st.session_state.pop(_KEY_TEXT_INPUT, None)
                st.rerun()

        if process_text_btn:
            text_to_process = text_content.strip()
            if not text_to_process:
                st.warning("⚠️ Teks kosong, silakan masukkan teks terlebih dahulu.")
            else:
                _run_text_pipeline(text_to_process, knowledge_base, auto_eval)

    # ── Hasil transkripsi (STT only) ─────────────────────────────────────────
    transcription = st.session_state.get(_KEY_TRANSCRIPTION)
    if transcription is not None:
        _handle_transcription_success(transcription, knowledge_base)


# =============================================================================
# CORE PIPELINE (runs RAG then redirects to 1_Hasil_Generate page)
# =============================================================================

def _run_rag_pipeline(audio_bytes: bytes, filename: str, provider: str, knowledge_base: str, auto_evaluate: bool = False):
    status_label = "⏳ Menjalankan Pipeline RAG & Evaluasi..." if auto_evaluate else "⏳ Menjalankan Pipeline RAG..."

    with st.status(status_label, expanded=True) as status:
        status.write(
            "🎙️ Mentranskripsi audio dan melakukan pencarian referensi hukum...")

        rag_response = process_audio_integrated(
            audio_bytes=audio_bytes,
            filename=filename,
            provider=provider,
            knowledge_base=knowledge_base,
            auto_evaluate=auto_evaluate,
            session_id=get_rag_session_id(),
        )

        if rag_response.get("status") == "error":
            status.update(label="❌ Pipeline RAG Gagal!",
                          state="error", expanded=True)
            st.error(f"Detail Error: {rag_response.get('error')}")
            return

        if auto_evaluate:
            status.write("📊 Mengambil dan memvalidasi skor evaluasi RAGAS...")

        status.update(
            label="✅ Semua proses selesai! Mengalihkan halaman...", state="complete")

    # ── REDIRECT DI LUAR BLOK STATUS (Setelah status complete) ──
    _handle_pipeline_success(rag_response, knowledge_base)


def _run_text_pipeline(text: str, knowledge_base: str, auto_evaluate: bool = False):
    """Run RAG pipeline from existing transcription text (no STT)."""
    status_label = "⏳ Menjalankan Pipeline RAG & Evaluasi..." if auto_evaluate else "⏳ Menjalankan Pipeline RAG..."

    # PERBAIKAN: Seluruh proses harus dikurung di dalam block status sampai selesai!
    with st.status(status_label, expanded=True) as status:
        status.write(
            "🔍 Mencari referensi hukum dan menyusun analisis dari teks...")

        rag_response = process_text_integrated(
            text=text,
            knowledge_base=knowledge_base,
            auto_evaluate=auto_evaluate,
            session_id=get_rag_session_id(),
        )

        if rag_response.get("status") == "error":
            status.update(label="❌ Pipeline RAG Gagal!",
                          state="error", expanded=True)
            st.error(f"Detail Error: {rag_response.get('error')}")
            return

        if auto_evaluate:
            status.write("📊 Mengambil dan memvalidasi skor evaluasi RAGAS...")

        status.update(
            label="✅ Semua proses selesai! Mengalihkan halaman...", state="complete")

    # ── REDIRECT DI LUAR BLOK STATUS ──
    _handle_pipeline_success(rag_response, knowledge_base)


# =============================================================================
# REFACTOR: Posisikan Pemindahan Halaman ke Helper Terpisah
# =============================================================================

def _handle_pipeline_success(rag_response: dict, knowledge_base: str):
    """Mengurus penyimpanan session state dan perpindahan halaman secara terpusat."""
    transcription = rag_response.get("transcription", {})
    material = rag_response.get("generated_material")
    rag_meta = rag_response.get("rag", {})
    context = rag_response.get("raw_context", "")
    question = transcription.get("repaired") or transcription.get("raw", "")

    set_last_rag_result(
        question=question,
        context=context,
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

    history_id = rag_response.get(
        "history_id") or rag_response.get("session_id")
    if history_id:
        st.session_state["current_session_id"] = history_id
        st.session_state.pop("selected_history_id", None)

    st.session_state["_force_refresh_history"] = True
    st.session_state.pop("_db_history_cache", None)

    # Lakukan redirect aman
    st.switch_page("pages/1_Hasil_Generate.py")
# =============================================================================
# HELPER
# =============================================================================


def _handle_transcription_success(transcription: str, knowledge_base: str):
    """Show editable transcription result with a button to run the full pipeline."""
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    st.success("✅ Transkripsi berhasil!")

    # Editable text area — user can review/edit before running pipeline
    edited_text = st.text_area(
        "Hasil Transkripsi (bisa diedit sebelum diproses):",
        value=transcription,
        height=150,
        key="transcription_preview",
    )

    # Update session state with edited text
    if edited_text != st.session_state.get(_KEY_TRANSCRIPTION):
        st.session_state[_KEY_TRANSCRIPTION] = edited_text

    # Buttons row
    col_process, col_clear = st.columns([3, 1])
    with col_process:
        process_from_text = st.button(
            "🚀  Proses dari Transkripsi",
            use_container_width=True,
            key="btn_process_from_text",
            type="primary",
            help="Jalankan pipeline RAG dari teks transkripsi ini (Repair → Search → Generate → Save).",
        )
    with col_clear:
        clear_transcription = st.button(
            "🗑️  Hapus",
            use_container_width=True,
            key="btn_clear_transcription",
            help="Hapus hasil transkripsi",
        )

    if clear_transcription:
        st.session_state.pop(_KEY_TRANSCRIPTION, None)
        st.rerun()

    if process_from_text:
        text_to_process = edited_text.strip()
        if not text_to_process:
            st.warning("⚠️ Teks transkripsi kosong, tidak bisa diproses.")
        else:
            auto_eval = st.session_state.get("toggle_auto_evaluate", False)
            _run_text_pipeline(text_to_process, knowledge_base, auto_eval)
