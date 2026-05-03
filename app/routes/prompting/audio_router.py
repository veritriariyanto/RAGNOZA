from fastapi import APIRouter, UploadFile, File, Query
from app.services.prompting.audio.stt_service import STTService

# Kita beri nama variable router agar mudah di-import
router = APIRouter()
stt_service = STTService()

@router.post("/ping")
async def test_connection():
    return {"status": "ok"}

@router.post("/process")
async def process_stt(
    file: UploadFile = File(...),
    provider: str = Query("whisper", enum=["whisper", "elevenlabs"])
):
    audio_data = await file.read()
    
    # Use the compatibility wrapper to route to the right provider
    text = await stt_service.transcribe(audio_data, provider=provider, filename=file.filename)
        
    return {
        "module": "prompting/audio",
        "transcription": text,
        "provider": provider,
        "model_used": "scribe_v1" if provider == "elevenlabs" else "whisper-large-v3",
        "transcription": text
    }