from fastapi import APIRouter, UploadFile, File, Query
from app.services.prompting.audio.stt_service import STTService

# Kita beri nama variable router agar mudah di-import
router = APIRouter()
stt_service = STTService()

@router.post("/process")
async def process_stt(
    file: UploadFile = File(...),
    provider: str = Query("whisper", enum=["whisper", "elevenlabs"])
):
    audio_data = await file.read()
    
    # Langsung panggil service. Validasi 5MB sudah otomatis berjalan di dalamnya.
    text = await stt_service.transcribe(
        audio_bytes=audio_data, 
        provider=provider, 
        filename=file.filename
    )
        
    return {
        "transcription": text,
        "provider": provider,
        "model_used": "scribe_v1" if provider == "elevenlabs" else "whisper-large-v3"
    }