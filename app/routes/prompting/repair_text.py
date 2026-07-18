from fastapi import APIRouter, UploadFile, File, Query, HTTPException
from pydantic import BaseModel
from app.services.prompting.audio.stt_service import STTService
from app.services.prompting.prompt.repair_text import text_refiner 

router = APIRouter()
stt_service = STTService()

class TextRepairRequest(BaseModel):
    text: str

@router.post("/process-audio")
async def process_audio_pipeline(
    file: UploadFile = File(...),
    provider: str = Query("whisper", enum=["whisper", "elevenlabs"])
):
    audio_data = await file.read()
    
    # 1. Jalankan Transkripsi
    raw_text = await stt_service.transcribe(
        audio_bytes=audio_data, 
        provider=provider, 
        filename=file.filename
    )
    
    if not raw_text:
        raise HTTPException(status_code=500, detail="Gagal melakukan transkripsi")

    # 2. Jalankan Repair Teks menggunakan method yang sudah diperbaiki
    refined_text = await text_refiner.repair_legal_text(raw_text)
        
    return {
        "status": "success",
        "method": "audio_pipeline",
        "original_transcription": raw_text,
        "refined_transcription": refined_text,
        "provider": provider
    }

@router.post("/process-text")
async def process_text_only(request: TextRepairRequest):
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Teks tidak boleh kosong")
    
    refined_text = await text_refiner.repair_legal_text(request.text)
    
    return {
        "status": "success",
        "method": "manual_text_repair",
        "original_text": request.text,
        "refined_text": refined_text
    }