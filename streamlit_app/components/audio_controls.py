import streamlit as st

from api.audio_api import transcribe_audio
from utils.session import get_current_session

def render_audio_controls():
    st.divider()

    st.subheader("🎤 Upload Audio")

    st.caption("Unggah file audio untuk ditranskripsi")

    # =========================================
    # AUDIO PROVIDER
    # =========================================
    provider = st.selectbox(
        "Pilih Provider:",
        [
            "whisper",
            "elevenlabs"
        ]
    )

    # =========================================
    # FILE UPLOADER
    # =========================================
    uploaded_audio = st.file_uploader(
        "Upload File Audio",
        type=[
            "mp3",
            "wav",
            "m4a",
            "ogg"
        ]
    )

    # =========================================
    # AUDIO PREVIEW
    # =========================================
    if uploaded_audio :
        st.audio(uploaded_audio)

        # =====================================
        # TRANSCRIBE BUTTON
        # =====================================
        if st.button (
            "Transcribe Audio",
            use_container_width=True
        ):
            with st.spinner("Sedang proses transcribe..."):
                response = transcribe_audio(
                    uploaded_audio,
                    provider
                ) 

            # =================================
            # ERROR
            # =================================
            if "error" in response:
                st.error(response["error"])
                return
            
            # =================================
            # SUCCESS
            # =================================
            transcription = response.get(
                "transcription", 
                ""
            )

            st.success("Transkripsi berhasil!")

            st.text_area(
                "Hasil Transkripsi:",
                transcription,
                height=200
            )

            # =================================
            # AUTO INSERT TO CHAT
            # =================================
            current_session = get_current_session()

            if current_session :
                current_session["messages"].append(
                    {
                        "role": "user",
                        "content": f"Transkripsi Audio: {transcription}"
                    }
                )

                st.info("Hasil transkripsi telah ditambahkan ke chat.")