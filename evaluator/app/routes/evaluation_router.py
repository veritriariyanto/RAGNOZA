"""
evaluator/app/routes/evaluation_router.py

Router FastAPI untuk evaluator service (port 8001).
Endpoint ini dipanggil oleh service utama (port 8000) sebagai background task HTTP POST.
"""

import logging

from fastapi import APIRouter, HTTPException

from app.schemas import EvaluationRequest, EvaluationResponse
from app.services.evaluation_service import EvaluationService

logger = logging.getLogger(__name__)
router = APIRouter()

evaluation_service = EvaluationService()


@router.post("/evaluate", response_model=EvaluationResponse)
async def evaluate(request: EvaluationRequest) -> EvaluationResponse:
    """
    Endpoint utama evaluasi RAGAS.

    Dipanggil oleh service utama (port 8000) setelah RAG pipeline selesai.
    Selalu berjalan async — tidak pernah memblokir response user.

    Flow:
        POST /api/v1/evaluate
            ← {question, context, answer, ground_truth?}
        → EvaluationResponse {status, metrics, error?}
    """
    try:
        result = await evaluation_service.run_evaluation(
            question=request.question,
            context=request.context,
            answer=request.answer,
            ground_truth=request.ground_truth,
            source_label=request.source_label,
        )
        return result

    except Exception as exc:
        logger.error("[/evaluate] Unhandled error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/evaluate/health")
async def evaluation_health():
    """Cek apakah RAGAS service siap menerima request."""
    from app.services.ragas_service import ragas_service

    return {
        "ragas_available": ragas_service.is_available,
        "error": ragas_service._availability_error,
    }