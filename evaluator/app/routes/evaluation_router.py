"""
evaluator/app/routes/evaluation_router.py

Router FastAPI untuk evaluator service (port 8001).
Endpoint ini dipanggil oleh service utama (port 8000) sebagai background task HTTP POST.
"""

import logging
from fastapi import APIRouter, HTTPException
from app.schemas.evaluation_schemas import EvaluationResponse, EvaluationRequest
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
    # Mengamankan logging dari nilai None (jika field bersifat optional di schema)
    q_log = request.question[:150] if getattr(request, 'question', None) else "KOSONG"
    ans_log = request.answer[:100] if getattr(request, 'answer', None) else "KOSONG"
    
    logger.info(
        "[Evaluator:8001] Request diterima | question='%s' | answer='%s'", 
        q_log, ans_log
    )
    
    try:
        # Memanggil service untuk mengeksekusi evaluasi matematika/LLM RAGAS
        result = await evaluation_service.run_evaluation(
            question=request.question,
            context=request.context,
            answer=request.answer,
            faithfulness_text=request.faithfulness_text,
            answer_qa=request.answer_qa,
            answer_risk=request.answer_risk,
            ground_truth=request.ground_truth,
            source_label=request.source_label or "rag_pipeline",
            is_reeval=request.is_reeval,
            existing_faithfulness=request.existing_faithfulness,
            existing_answer_relevancy=request.existing_answer_relevancy,
            existing_risk_faithfulness=request.existing_risk_faithfulness,
            existing_overall=request.existing_overall,
            existing_segments=request.existing_segments or [],
            context_chunks=request.context_chunks or [], 
            existing_faithfulness_summary=request.existing_faithfulness_summary,   # ← FIX #7
            existing_faithfulness_qa=request.existing_faithfulness_qa,
            skip_answer_relevancy=request.skip_answer_relevancy,   # ← FIX #8
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