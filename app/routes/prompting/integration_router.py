# app/routes/prompting/audio_router.py
from fastapi import APIRouter, UploadFile, File, Query, Depends, HTTPException
from app.services.prompting.audio.stt_service import STTService
from app.services.prompting.prompt.repair_text import TextRefinerService
from app.services.knowledgebase.qdrant_storage import QdrantStorage
from app.services.prompting.integration.rag_integration_service import RAGIntegrationService
router = APIRouter()

# Inisialisasi Service (Bisa ditaruh di file dependencies.py jika ingin lebih global)
def get_rag_service():
    stt = STTService()
    refiner = TextRefinerService()
    qdrant = QdrantStorage(
        db=qdrant_db.client, 
        embeddings=embeddings
    )
    return RAGIntegrationService(stt, refiner, qdrant)

@router.post("/process-integrated")
async def process_audio_rag(
    file: UploadFile = File(...),
    provider: str = Query("whisper", enum=["whisper", "elevenlabs"]),
    knowledge_base: str = Query("uud_1945"),
    rag_service: RAGIntegrationService = Depends(get_rag_service)
):
    """
    Endpoint terintegrasi untuk memproses audio hingga mendapatkan konteks RAG.
    Alur: Audio -> STT -> Repair/Query Extraction -> Qdrant Search -> Final Context.
    """
    try:
        audio_data = await file.read()
        
        # Memanggil konduktor service yang sudah kita buat sebelumnya
        result = await rag_service.process_audio_to_knowledge(
            audio_bytes=audio_data,
            filename=file.filename,
            knowledge_base=knowledge_base,
            provider=provider
        )
        
        return {
            "status": "success",
            "provider": provider,
            "data": {
                "transcription": {
                    "raw": result["raw_transcribe"],
                    "repaired": result["final_repaired_text"]
                },
                "rag": {
                    "query_used": result["search_query_used"],
                    "has_context": result["has_context"],
                    "context": result["retrieved_context"]
                }
            }
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")