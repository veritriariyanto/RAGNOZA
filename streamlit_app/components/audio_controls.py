# streamlit_app/components/audio_controls.py

import streamlit as st
import requests
from streamlit_mic_recorder import mic_recorder

from utils.session import get_current_session, set_pending_audio_text
from config.settings import settings

BASE_URL = settings.API_BASE_URL

# =========================================
# SESSION STATE KEYS
# =========================================
_KEY_UPLOAD_BYTES   = "_audio_upload_bytes"
_KEY_UPLOAD_NAME    = "_audio_upload_name"
_KEY_RECORD_BYTES   = "_audio_record_bytes"
_KEY_TRANSCRIPTION  = "_audio_transcription"


def _transcribe(audio_bytes: bytes, filename: str, provider: str) -> tuple[str | None, str | None]:
    """
    Kirim audio ke FastAPI /audio/process.
    Return (transcription, error_message).
    """
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


def render_audio_controls():

    st.divider()
    st.subheader("🎙️ Audio ke Teks")
    st.caption("Upload file audio atau rekam langsung — hasil transkripsi otomatis masuk ke chat.")

    # =========================================
    # PROVIDER SELECTOR
    # =========================================
    provider = st.selectbox(
        "Provider STT:",
        ["whisper", "elevenlabs"],
        help="Whisper (Groq) — cepat & gratis. ElevenLabs Scribe — akurasi tinggi.",
    )

    # =========================================
    # TAB: UPLOAD  |  RECORD
    # =========================================
    tab_upload, tab_record = st.tabs(["📂 Upload File", "🔴 Rekam Langsung"])

    # ------------------------------------------
    # TAB 1 — UPLOAD FILE
    # ------------------------------------------
    with tab_upload:

        uploaded_audio = st.file_uploader(
            "Pilih file audio",
            type=["mp3", "wav", "m4a", "ogg", "webm"],
            label_visibility="collapsed",
            # Gunakan on_change untuk menyimpan bytes ke session_state
            # sebelum widget direset oleh rerun
            key="audio_file_uploader",
        )

        # Simpan ke session_state saat file baru dipilih
        # (widget masih hidup di titik ini, jadi .read() aman)
        if uploaded_audio is not None:
            st.session_state[_KEY_UPLOAD_BYTES] = uploaded_audio.read()
            st.session_state[_KEY_UPLOAD_NAME]  = uploaded_audio.name

        # Ambil dari session_state (tetap ada meski rerun)
        upload_bytes = st.session_state.get(_KEY_UPLOAD_BYTES)
        upload_name  = st.session_state.get(_KEY_UPLOAD_NAME, "audio.wav")

        if upload_bytes:
            st.audio(upload_bytes)

            col_btn, col_clear = st.columns([3, 1])
            with col_btn:
                transcribe_upload = st.button(
                    "▶️ Transkripsi File",
                    use_container_width=True,
                    key="btn_transcribe_upload",
                )
            with col_clear:
                if st.button("🗑️", use_container_width=True, key="btn_clear_upload",
                             help="Hapus file"):
                    st.session_state.pop(_KEY_UPLOAD_BYTES, None)
                    st.session_state.pop(_KEY_UPLOAD_NAME, None)
                    st.session_state.pop(_KEY_TRANSCRIPTION, None)
                    st.rerun()

            if transcribe_upload:
                # Hapus hasil transkripsi lama
                st.session_state.pop(_KEY_TRANSCRIPTION, None)
                with st.spinner("Sedang memproses transkripsi..."):
                    transcription, error = _transcribe(
                        audio_bytes=upload_bytes,
                        filename=upload_name,
                        provider=provider,
                    )
                if error:
                    st.error(f"⚠️ {error}")
                else:
                    st.session_state[_KEY_TRANSCRIPTION] = transcription
                    st.rerun()

    # ------------------------------------------
    # TAB 2 — REKAM LANGSUNG
    # ------------------------------------------
    with tab_record:
        st.caption("Klik **Start** untuk mulai merekam, **Stop** untuk menyelesaikan.")

        # mic_recorder mengembalikan dict {"bytes": ..., "id": ...} atau None.
        # just_once=True berarti ia akan mengembalikan data SEKALI lalu reset —
        # kita harus langsung simpan ke session_state di sini.
        audio_data = mic_recorder(
            start_prompt="🔴 Start Rekam",
            stop_prompt="⏹️ Stop Rekam",
            just_once=True,
            use_container_width=True,
            key="mic_recorder",
        )

        # Simpan bytes rekaman ke session_state saat baru tersedia
        if audio_data and audio_data.get("bytes"):
            st.session_state[_KEY_RECORD_BYTES] = audio_data["bytes"]
            # Hapus transkripsi lama dari sesi rekaman sebelumnya
            st.session_state.pop(_KEY_TRANSCRIPTION, None)

        record_bytes = st.session_state.get(_KEY_RECORD_BYTES)

        if record_bytes:
            st.audio(record_bytes, format="audio/wav")

            col_btn, col_clear = st.columns([3, 1])
            with col_btn:
                transcribe_record = st.button(
                    "▶️ Transkripsi Rekaman",
                    use_container_width=True,
                    key="btn_transcribe_record",
                )
            with col_clear:
                if st.button("🗑️", use_container_width=True, key="btn_clear_record",
                             help="Hapus rekaman"):
                    st.session_state.pop(_KEY_RECORD_BYTES, None)
                    st.session_state.pop(_KEY_TRANSCRIPTION, None)
                    st.rerun()

            if transcribe_record:
                st.session_state.pop(_KEY_TRANSCRIPTION, None)
                with st.spinner("Sedang memproses transkripsi rekaman..."):
                    transcription, error = _transcribe(
                        audio_bytes=record_bytes,
                        filename="recording.wav",
                        provider=provider,
                    )
                if error:
                    st.error(f"⚠️ {error}")
                else:
                    st.session_state[_KEY_TRANSCRIPTION] = transcription
                    st.rerun()

    # =========================================
    # HASIL TRANSKRIPSI — ditampilkan di luar
    # tab agar tidak ikut hilang saat tab switch
    # =========================================
    transcription = st.session_state.get(_KEY_TRANSCRIPTION)
    if transcription is not None:
        _handle_transcription_success(transcription)


# =========================================
# HELPER — handle hasil transkripsi berhasil
# =========================================
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
                # Bersihkan hasil transkripsi setelah dikirim
                st.session_state.pop(_KEY_TRANSCRIPTION, None)
                st.info("✅ Teks dikirim ke chat input.")
                st.rerun()

    with col_copy:
        st.code(transcription, language=None)