"""
generate_content_routes.py  (updated)

Perubahan dari versi lama:
- Tambah endpoint /generate-with-eval yang menjalankan RAGAS otomatis
- Endpoint /generate lama tetap tidak berubah (backward compatible)
- Evaluasi berjalan di BackgroundTask — tidak memperlambat response
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.core.postgres import get_db
from app.schemas.prompting.generate_content import MaterialRequest, MaterialResponse
from app.services.evaluation.evaluation_hook import trigger_auto_evaluation
from app.services.evaluation.formatter import material_to_text
from app.services.history.session_service import SessionService
from app.services.prompting.prompt.generate_content_service import material_service

from sqlalchemy.orm import Session

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Helper: Simpan ke Database ────────────────────────────────────────────────

def _save_to_database(
    db: Session,
    payload: MaterialRequest,
    result: MaterialResponse,
    provider: str = "direct_generate",
) -> int | None:
    """
    Menyimpan hasil generate material ke tabel rag_process dan rag_session.
    Returns history_id jika berhasil, None jika gagal.
    """
    try:
        session_title = payload.user_scenario[:80] if payload.user_scenario else "Generate Tanpa Judul"
        saved_history = SessionService.save_history(
            db=db,
            session_id=None,
            session_title=session_title,
            knowledge_base="direct_input",
            provider=provider,
            raw_transcribe=payload.user_scenario,
            repaired_text=payload.user_scenario,
            search_query=payload.user_scenario,
            retrieved_context=payload.context_text,
            final_material=result,
        )
        if saved_history:
            logger.info(
                "[GenerateContent] Tersimpan ke database — history_id=%d", saved_history.id
            )
            return saved_history.id
        return None
    except Exception as exc:
        logger.error("[GenerateContent] Gagal simpan ke database: %s", exc, exc_info=True)
        return None


# ── Endpoint Lama (sekarang dengan penyimpanan database) ──────────────────────

@router.post(
    "/generate",
    response_model=MaterialResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Legal Material (tersimpan di database)",
)
async def create_material(
    payload: MaterialRequest,
    db: Session = Depends(get_db),
):
    """
    Generate material hukum dari konteks teks.
    Hasil generate otomatis disimpan ke database (rag_process & rag_session).
    """
    try:
        result = await material_service.generate_legal_material(payload)

        # Simpan ke database
        _save_to_database(db, payload, result, provider="direct_generate")

        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal generate material: {str(exc)}",
        )


# ── Endpoint Baru: Generate + Simpan Database + Evaluasi Background ───────────

@router.post(
    "/generate-with-eval",
    response_model=MaterialResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Legal Material (tersimpan + evaluasi background)",
    description="""
    Generate material hukum dari konteks teks.
    - Hasil generate otomatis disimpan ke database (rag_process & rag_session)
    - Evaluasi RAGAS berjalan otomatis di **background** setelah response dikirim

    **Metrik yang dievaluasi:**
    - Faithfulness
    - Answer Relevancy
    - Context Precision *(proxy ground truth dari context)*
    - Context Recall *(proxy ground truth dari context)*
    """,
)
async def create_material_with_evaluation(
    payload: MaterialRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Args:
        payload.context_text  : Teks konteks hukum yang di-retrieve
        payload.user_scenario : Skenario / pertanyaan user

    Returns:
        MaterialResponse — hasil generate material.
        Hasil disimpan ke database dan evaluasi RAGAS berjalan di background.
    """
    try:
        result = await material_service.generate_legal_material(payload)

        # Simpan ke database
        history_id = _save_to_database(db, payload, result, provider="generate_with_eval")

        # Jalankan evaluasi di background jika ada history_id
        if history_id and payload.context_text and result:
            material_text = material_to_text(result)
            background_tasks.add_task(
                trigger_auto_evaluation,
                question=payload.user_scenario,
                context=payload.context_text,
                material=result,
                ground_truth=None,
                source_label="generate_content",
                history_id=history_id,
            )

        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal generate material: {str(exc)}",
        )


