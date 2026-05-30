"""
integration_router.py  (updated)

Perubahan dari versi lama:
- Tambah parameter BackgroundTasks dari FastAPI
- BackgroundTasks diteruskan ke RAGIntegrationService.process_audio_to_material()
  agar evaluasi RAGAS berjalan di background (tidak blocking response user)
"""

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile

from app.core.embeddings import embeddings
from app.core.postgres import get_db
from app.core.qdrant import qdrant_db
from app.services.knowlagebase.qdrant_storage import QdrantStorage
from app.services.prompting.audio.stt_service import STTService
from app.services.prompting.integration.rag_integration_service import RAGIntegrationService
from app.services.prompting.prompt.generate_content_service import MaterialGeneratorService
from app.services.prompting.prompt.repair_text import TextRefinerService

from sqlalchemy.orm import Session

router = APIRouter()


# ── Dependency ────────────────────────────────────────────────────────────────

async def get_rag_service(db: Session = Depends(get_db)) -> RAGIntegrationService:
    """Bangun RAGIntegrationService dengan semua dependency-nya."""
    stt = STTService()
    refiner = TextRefinerService()
    material_gen = MaterialGeneratorService()
    qdrant = QdrantStorage(db=qdrant_db.client, embeddings=embeddings)

    return RAGIntegrationService(
        stt_service=stt,
        text_service=refiner,
        vector_service=qdrant,
        material_service=material_gen,
        db=db,
    )


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post(
    "/process-integrated",
    summary="RAG Pipeline Terintegrasi (Audio → STT → Search → Material)",
    description="""
    Endpoint terintegrasi penuh RAG:
    **Audio → STT → Repair Text → Search Qdrant → Generate Material**

    Evaluasi RAGAS berjalan otomatis di **background** setelah response dikirim ke user
    (tidak memperlambat waktu respons). Hasil evaluasi dapat dilihat di log server.

    **Metrik yang dievaluasi otomatis:**
    - Faithfulness
    - Answer Relevancy
    - Context Precision *(jika ground truth tersedia)*
    - Context Recall *(jika ground truth tersedia)*
    """,
)
async def process_audio_rag(
    background_tasks: BackgroundTasks,                          # ← BARU
    file: UploadFile = File(...),
    provider: str = Query("whisper", enum=["whisper", "elevenlabs"]),
    knowledge_base: str = Query("uud_1945"),
    style: str = Query("formal", enum=["formal", "casual", "academic"]),
    rag_service: RAGIntegrationService = Depends(get_rag_service),
):
    """
    Args:
        file            : File audio (MP3, WAV, dll)
        provider        : Provider STT (whisper / elevenlabs)
        knowledge_base  : Nama collection di Qdrant
        style           : Gaya penulisan material

    Returns:
        Hasil RAG pipeline lengkap. Evaluasi RAGAS berjalan di background.
    """
    try:
        audio_data = await file.read()

        result = await rag_service.process_audio_to_material(
            audio_bytes=audio_data,
            filename=file.filename,
            knowledge_base=knowledge_base,
            provider=provider,
            style=style,
            background_tasks=background_tasks,              # ← BARU: teruskan ke service
        )

        # integration_router.py — di dalam process_audio_rag, sebelum return
        full_ctx = result.retrieved_context or ""
        print(f"[ROUTER DEBUG] retrieved_context length: {len(full_ctx)}")
        print(f"[ROUTER DEBUG] retrieved_context preview: {repr(full_ctx[:200])}")
        print(f"[ROUTER DEBUG] source_details count: {len(result.source_details)}")
        print(f"[ROUTER DEBUG] source_details[0] keys: {list(result.source_details[0].keys()) if result.source_details else 'EMPTY'}")

        return {
            "status": "success",
            "provider": provider,
            "knowledge_base": knowledge_base,
            "data": {
                "transcription": {
                    "raw": result.raw_transcribe,
                    "repaired": result.final_repaired_text,
                },
                "rag": {
                    "query_used": result.search_query_used,
                    "has_context": result.has_context,
                    "context_preview": (
                        result.retrieved_context[:500] + "..."
                        if len(result.retrieved_context) > 500
                        else result.retrieved_context
                    ),
                    "full_context": result.retrieved_context or "",  # ← tambah ini
                    "sources_count": len(result.source_details),
                },

                "generated_material": (
                    result.final_material.model_dump() if result.final_material else None
                ),
                "fallback_message": result.fallback_message,
            },
            # Info untuk user bahwa evaluasi berjalan di background
            "evaluation": {
                "status": "running_in_background",
                "note": (
                    "Evaluasi RAGAS berjalan otomatis di background. "
                    "Lihat log server untuk hasil metrik."
                ),
            },
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"RAG Integration Error: {str(exc)}",
        )