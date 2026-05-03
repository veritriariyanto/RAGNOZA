from fastapi import APIRouter, UploadFile, File, Query
from app.services.prompting.audio.stt_service import STTService

# Kita beri nama variable router agar mudah di-import
router = APIRouter()
stt_service = STTService()

@router.post("/test-koneksi")
async def transcribe():
    return {"status": "ok"}

@router.post("/process")
async def process_stt(
    file: UploadFile = File(...),
    provider: str = Query("whisper", enum=["whisper", "elevenlabs"])
):
    audio_data = await file.read()
    
    if provider == "whisper":
        text = await stt_service.transcribe_with_whisper(audio_data, file.filename)
    else:
        text = await stt_service.transcribe_with_elevenlabs(audio_data)
        
    return {
        "module": "prompting/audio",
        "transcription": text
    }