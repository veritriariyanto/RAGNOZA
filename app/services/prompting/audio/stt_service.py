import io
from app.core.stt_provider import groq_client, el_client

class STTService:
    @staticmethod
    async def transcribe_with_whisper(audio_file: bytes, filename: str):
        """Transkripsi menggunakan Groq Whisper (Cepat & Akurat)"""
        try:
            # Groq mengharapkan file-like object
            transcription = groq_client.audio.transcriptions.create(
                file=(filename, audio_file),
                model="whisper-large-v3",
                response_format="text"
            )
            return transcription
        except Exception as e:
            raise Exception(f"Whisper Error: {str(e)}")

    @staticmethod
    async def transcribe_with_elevenlabs(audio_file: bytes):
        """Transkripsi menggunakan ElevenLabs STT"""
        try:
            # Konversi bytes ke file-like object untuk ElevenLabs
            audio_io = io.BytesIO(audio_file)
            response = el_client.speech_to_text.convert(
                file=audio_io,
                model_id="scribe_v1", # Model terbaru ElevenLabs
            )
            return response.text
        except Exception as e:
            raise Exception(f"ElevenLabs Error: {str(e)}")