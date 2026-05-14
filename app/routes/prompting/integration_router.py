# app/routes/prompting/integration_router.py
from fastapi import APIRouter, UploadFile, File, Query, Depends, HTTPException
from app.core.qdrant import qdrant_db
from app.services.prompting.audio.stt_service import STTService
from app.services.prompting.prompt.repair_text import TextRefinerService
from app.services.prompting.prompt.generate_content_service import MaterialGeneratorService
from app.services.knowledgebase.qdrant_storage import QdrantStorage
from app.services.prompting.integration.rag_integration_service import RAGIntegrationService

# Import embeddings yang sudah Anda buat
from langchain_huggingface import HuggingFaceEmbeddings

router = APIRouter()

# Inisialisasi embeddings (sama seperti yang Anda gunakan di tempat lain)
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

# Dependency untuk RAG Service
def get_rag_service():
    stt = STTService()
    refiner = TextRefinerService()
    material_gen = MaterialGeneratorService()
    
    qdrant = QdrantStorage(
        db=qdrant_db.client, 
        embeddings=embeddings
    )
    
    return RAGIntegrationService(stt, refiner, qdrant, material_gen)

@router.post("/process-integrated")
async def process_audio_rag(
    file: UploadFile = File(...),
    provider: str = Query("whisper", enum=["whisper", "elevenlabs"]),
    knowledge_base: str = Query("test"),
    style: str = Query("formal", enum=["formal", "casual", "academic"]),
    rag_service: RAGIntegrationService = Depends(get_rag_service)
):
    """
    Endpoint terintegrasi penuh RAG:
    Audio -> STT -> Repair Text -> Search Qdrant -> Generate Material
    
    Args:
        file: File audio (MP3, WAV, dll)
        provider: Provider STT (whisper/elevenlabs)
        knowledge_base: Nama collection di Qdrant
        style: Gaya penulisan material (formal/casual/academic)
    
    Returns:
        Complete RAG pipeline result with final generated material
    """
    try:
        audio_data = await file.read()
        
        # Process melalui full RAG pipeline
        result = await rag_service.process_audio_to_material(
            audio_bytes=audio_data,
            filename=file.filename,
            knowledge_base=knowledge_base,
            provider=provider,
            style=style
        )
        
        return {
            "status": "success",
            "provider": provider,
            "knowledge_base": knowledge_base,
            "data": {
                "transcription": {
                    "raw": result.raw_transcribe,
                    "repaired": result.final_repaired_text
                },
                "rag": {
                    "query_used": result.search_query_used,
                    "has_context": result.has_context,
                    "context_preview": result.retrieved_context[:500] + "..." if len(result.retrieved_context) > 500 else result.retrieved_context,
                    "sources_count": len(result.source_details)
                },
                "generated_material": result.final_material.model_dump() if result.final_material else None
            }
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"RAG Integration Error: {str(e)}"
        )