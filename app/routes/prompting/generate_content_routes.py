"""
generate_content_routes.py  (updated)

Perubahan dari versi lama:
- Tambah endpoint /generate-with-eval yang menjalankan RAGAS otomatis
- Endpoint /generate lama tetap tidak berubah (backward compatible)
- Evaluasi berjalan di BackgroundTask — tidak memperlambat response
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from app.schemas.prompting.generate_content import MaterialRequest, MaterialResponse
from app.services.evaluation.evaluation_hook import trigger_auto_evaluation
from app.services.evaluation.formatter import material_to_text
from app.services.prompting.prompt.generate_content_service import material_service

router = APIRouter()


# ── Endpoint Lama (tidak berubah, backward compatible) ────────────────────────

@router.post(
    "/generate",
    response_model=MaterialResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Legal Material (tanpa evaluasi)",
)
async def create_material(payload: MaterialRequest):
    """
    Generate material hukum dari konteks teks.
    Tidak menjalankan evaluasi RAGAS.
    """
    try:
        result = await material_service.generate_legal_material(payload)
        return result
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal generate material: {str(exc)}",
        )


# ── Endpoint Baru: Generate + Evaluasi Otomatis ───────────────────────────────

@router.post(
    "/generate-with-eval",
    response_model=MaterialResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Legal Material (evaluasi dilakukan oleh frontend)",
    description="""

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
):
    """
    Args:
        payload.context_text  : Teks konteks hukum yang di-retrieve
        payload.user_scenario : Skenario / pertanyaan user

    Returns:
        MaterialResponse — hasil generate material.
        Evaluasi RAGAS berjalan di background setelah response dikirim.
    """
    try:
        result = await material_service.generate_legal_material(payload)
        return result  # evaluasi dilakukan frontend, tidak perlu di sini
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal generate material: {str(exc)}",
        )