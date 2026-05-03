import io
from app.core.stt_provider import groq_client, el_client

class STTService:
    @staticmethod
    async def transcribe_with_whisper(audio_bytes: bytes, filename: str) -> str:
        """Menggunakan Groq Whisper v3"""
        try:
            # Groq butuh tuple (nama_file, content)
            transcription = groq_client.audio.transcriptions.create(
                file=(filename, audio_bytes),
                model="whisper-large-v3",
                response_format="text"
            )
            return transcription
        except Exception as e:
            raise Exception(f"Groq Whisper Error: {str(e)}")

    @staticmethod
    async def transcribe_with_elevenlabs(audio_bytes: bytes) -> str:
        """Menggunakan ElevenLabs Scribe v1"""
        try:
            # ElevenLabs butuh file-like object
            audio_stream = io.BytesIO(audio_bytes)
            response = el_client.speech_to_text.convert(
                file=audio_stream,
                model_id="scribe_v1",
            )
            return response.text
        except Exception as e:
            raise Exception(f"ElevenLabs Error: {str(e)}")