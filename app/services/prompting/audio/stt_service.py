import io
from app.core.stt_provider import groq_client, el_client
from fastapi import HTTPException
import asyncio

class STTService:
    MAX_FILE_SIZE = 5 * 1024 * 1024
    TIMEOUT_SECONDS = 30

    STT_CONTEXT_PROMPT = (
        "Transkripsi resmi Undang-Undang Dasar Negara Republik Indonesia 1945. "
        "Gunakan ejaan resmi PUEBI. Pastikan istilah hukum ditulis dengan benar: "
        "UUD 1945, Amandemen, Konstitusi, Pasal, Ayat, Preambule, "
        "Mahkamah Konstitusi, DPR, MPR, dan Yudikatif."
    )

    def validate_audio(self, audio_bytes: bytes):
        """Fungsi khusus untuk mengecek kelayakan audio sebelum di-transcribe"""
        size_mb = len(audio_bytes) / (1024 * 1024)
        
        if len(audio_bytes) > self.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File terlalu besar! Maksimal 5 MB. File Anda: {size_mb:.2f} MB"
            )
    @staticmethod
    async def transcribe_with_whisper(audio_bytes: bytes, filename: str) -> str:
        """Menggunakan Groq Whisper v3"""
        print("[System] Memulai proses transkripsi via Whisper Large v3")
        try:
            # Jalankan call sinkron di thread agar timeout asyncio tetap efektif.
            transcription = await asyncio.to_thread(
                lambda: groq_client.audio.transcriptions.create(
                    file=(filename, audio_bytes),
                    model="whisper-large-v3",
                    prompt=STTService.STT_CONTEXT_PROMPT,
                    response_format="text"
                )
            )
            print("[System] Transkripsi Whisper Berhasil!")
            return transcription
        except Exception as e:
            raise Exception(f"Groq Whisper Error: {str(e)}")

    @staticmethod
    async def transcribe_with_elevenlabs(audio_bytes: bytes) -> str:
        """Menggunakan ElevenLabs Scribe v1"""
        print("[System] Memulai proses transkripsi via ElevenLabs Scribe v1")
        try:
            # ElevenLabs butuh file-like object
            audio_stream = io.BytesIO(audio_bytes)
            response = await asyncio.to_thread(
                lambda: el_client.speech_to_text.convert(
                    file=audio_stream,
                    model_id="scribe_v1",
                    language_code="id",
                    tag_and_track=True,
                )
            )
            print("[System] Transkripsi ElevenLabs Berhasil!")
            return response.text
        except Exception as e:
            raise Exception(f"ElevenLabs Error: {str(e)}")

    async def transcribe(self, audio_bytes: bytes, provider: str = "whisper", filename: str | None = None) -> str:
        self.validate_audio(audio_bytes)

        provider = (provider or "").lower()

        try:
            if provider == "whisper":
                if not filename:
                    raise ValueError("'filename' is required when using whisper provider")
                return await asyncio.wait_for(
                    self.transcribe_with_whisper(audio_bytes, filename), 
                    timeout=self.TIMEOUT_SECONDS
                )
            
            elif provider == "elevenlabs":
                return await asyncio.wait_for(
                    self.transcribe_with_elevenlabs(audio_bytes), 
                    timeout=self.TIMEOUT_SECONDS
                )
            
            else:
                raise ValueError(f"Unknown STT provider: {provider}")

        except asyncio.TimeoutError:
            print(f"[Error] Transkripsi dibatalkan karena melebihi {self.TIMEOUT_SECONDS} detik")
            raise HTTPException(
                status_code=504, 
                detail="Proses terlalu lama (Timeout). Silakan periksa koneksi atau coba file yang lebih pendek."
            )