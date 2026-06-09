import logging
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.embeddings import embeddings
from app.core.postgres import get_db
from app.core.qdrant import qdrant_db
from app.services.knowlagebase.qdrant_storage import QdrantStorage
from app.services.prompting.audio.stt_service import STTService
from app.services.prompting.integration.rag_integration_service import RAGIntegrationService
from app.services.prompting.prompt.generate_content_service import MaterialGeneratorService
from app.services.prompting.prompt.repair_text import TextRefinerService

# Inisialisasi logger agar seragam dengan modul service
logger = logging.getLogger(__name__)

router = APIRouter()


# ── Dependency ────────────────────────────────────────────────────────────────

async def get_rag_service(db: Session = Depends(get_db)) -> RAGIntegrationService:
    """
    Bangun RAGIntegrationService dengan semua dependency-nya secara aman.
    """
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
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="File audio input (MP3, WAV, dsb)"),
    provider: str = Query("whisper", enum=["whisper", "elevenlabs"], description="Provider mesin STT"),
    knowledge_base: str = Query("uud_1945", description="Nama collection/basis pengetahuan di Qdrant"),
    auto_evaluate: bool = Query(True, description="Apakah otomatis menjalankan evaluasi Ragas di background"),
    rag_service: RAGIntegrationService = Depends(get_rag_service),
):
    logger.info(f"Menerima permintaan RAG terintegrasi. Provider STT: '{provider}', KB: '{knowledge_base}'")
    
    try:
        # Membaca file biner audio
        audio_data = await file.read()

        # Eksekusi RAG Pipeline utama
        result = await rag_service.process_audio_to_material(
            audio_bytes=audio_data,
            filename=file.filename,
            knowledge_base=knowledge_base,
            provider=provider,
            background_tasks=background_tasks,
            auto_evaluate=auto_evaluate,
        )

        # --- Safe Attribute Extraction (Mengikuti Style Service) ---
        # Menghindari kegagalan parsing dengan mengamankan nilai fallback default
        full_ctx = getattr(result, "retrieved_context", None) or getattr(result, "context", "") or ""
        source_details = getattr(result, "source_details", []) or []
        session_id_val = getattr(result, "session_id", None)

        # Mengganti print() bawaan dengan Logger terstruktur untuk monitoring produksi
        logger.debug(f"[ROUTER] Panjang retrieved_context: {len(full_ctx)} karakter")
        logger.debug(f"[ROUTER] Jumlah source_details: {len(source_details)}")
        if source_details and isinstance(source_details, list):
            logger.debug(f"[ROUTER] Tipe data elemen sumber pertama: {type(source_details[0])}")

        # Mengembalikan response terstruktur (Sesuai gaya penanganan format JSON di sistem)
        return {
            "status": "success",
            "provider": provider,
            "knowledge_base": knowledge_base,
            "data": {
                "transcription": {
                    "raw": getattr(result, "raw_transcribe", "-"),
                    "repaired": getattr(result, "final_repaired_text", "-"),
                },
                "rag": {
                    "query_used": getattr(result, "search_query_used", "-"),
                    "has_context": getattr(result, "has_context", False),
                    "context_preview": (
                        full_ctx[:500] + "..."
                        if len(full_ctx) > 500
                        else full_ctx
                    ),
                    "full_context": full_ctx,
                    "sources_count": len(source_details),
                },
                "generated_material": (
                    result.final_material.model_dump() 
                    if getattr(result, "final_material", None) else None
                ),
                "fallback_message": getattr(result, "fallback_message", None),
                "history_id": getattr(result, "history_id", None),
            },
            "evaluation": {
                "status": "running_in_background" if auto_evaluate else "disabled",
                "enabled": auto_evaluate,
                "note": (
                    "Evaluasi RAGAS berjalan otomatis di background. "
                    "Hasil akhir metrik akan dicatat pada log server atau database evaluasi."
                    if auto_evaluate else "Evaluasi dinonaktifkan melalui parameter request."
                ),
            },
        }

    except HTTPException as http_exc:
        # Meneruskan langsung jika yang terjadi adalah HTTP Exception resmi dari sistem
        logger.warning(f"HTTP Exception terdeteksi di router: {http_exc.detail}")
        raise http_exc
        
    except Exception as exc:
        # Menangani kegagalan total sistem dengan log yang jelas dan respons kode 500 yang aman
        logger.error(f"Kegagalan fatal pada RAG Integration Router: {str(exc)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"RAG Integration Internal Error: {str(exc)}",
        )