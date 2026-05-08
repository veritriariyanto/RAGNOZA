import streamlit as st
import requests

st.set_page_config(
    page_title="RAG ChatBot - UUD Decision Support With Audio STT",
    page_icon="🎤",
    layout="centered",

)

#Judul Aplikasi 
st.title("RAG ChatBot - UUD Decision Support")

st.write("Upload file audio Anda (maksimal 5 MB) untuk mendapatkan transkripsi teks yang dapat digunakan dalam sistem RAG kami.")

#Upload audio 
uploaded_file = st.file_uploader(
    "Upload file audio Anda (format: .mp3, .wav, .ogg, dll.)",
    type=["mp3", "wav", "ogg", "m4a", "flac"]
)

#Pilih Provider STT
provider_display = st.selectbox(
    "Pilih Provider Transkripsi:",
    ["Whisper (Groq)", "ElevenLabs Scribe v1"]
)

#Mapping display name -> nilai backend
provider_map = {
    "Whisper (Groq)" : "whisper",
    "ElevenLabs Scribe v1" : "elevenlabs"
}
provider = provider_map[provider_display]

#Tombol proses 
if st.button("Proses Audio Transkripsi"):
    if uploaded_file is not None:
        with st.spinner("Memproses Audio..."):
            try:
                files = {
                    "file": (
                        uploaded_file.name,
                        uploaded_file,
                        uploaded_file.type
                    )
                }

                params = {
                    "provider": provider
                }

                response = requests.post(
                    "http://127.0.0.1:8000/prompting/audio/process",
                    files=files,
                    params=params
                )
                
                st.write("Status", response.status_code)
                st.code(response.text)
                
                result = response.json()

                st.success("Audio berhasil diproses!")

                st.subheader("Hasil Transkripsi:")
                st.write(result["transcription"])

                st.subheader("Informasi")
                st.write(f"Provider: {result['provider']}")
                st.write(f"Model: {result['model_used']}")

            except Exception as e:
                st.error(f"Terjadi error: {e}")

    else: 
        st.warning("Silahkan upload file audio terlebih dahulu!")
                
        