# app/routes/evaluasi/evaluation_router.py
#
# Router ini sekarang memanggil evaluator service (port 8001) via HTTP.
# EvaluationService dan RagasService sudah dipindah ke evaluator/ — tidak lagi
# diimport langsung di sini untuk menghindari konflik dependency ragas vs langchain.

import os
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.postgres import get_db
from app.schemas.evaluasi.evaluation import EvaluationRequest, EvaluationResponse
from app.services.evaluation.formatter import material_to_text
from app.services.history.rag_history_service import RAGHistoryService
from app.schemas.prompting.generate_content import MaterialResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Evaluation"])

EVALUATOR_BASE_URL = os.getenv("EVALUATOR_URL", "http://localhost:8001")
EVALUATOR_ENDPOINT = f"{EVALUATOR_BASE_URL}/api/v1/evaluate"
# Evaluasi 4 metrik bisa memakan waktu lama, apalagi jika antre di semaphore.
# Timeout dibuat lebih longgar agar request tidak diputus sebelum evaluator selesai.
EVALUATOR_TIMEOUT = float(os.getenv("EVALUATOR_TIMEOUT_SECONDS", "900"))

# Endpoint untuk konversi MaterialResponse ke teks plain (untuk RAGAS) dari json menjadi plain text
@router.post(
    "/material-to-text",
    summary="Konversi MaterialResponse ke teks plain untuk RAGAS",
    description="Endpoint internal — dipanggil frontend setelah generate material.",
)
async def convert_material_to_text(material: MaterialResponse):
    """
    Menerima MaterialResponse (dict) dan mengembalikan teks plain.
    Frontend tidak perlu tahu format internal MaterialResponse.
    Jika schema berubah, hanya formatter.py yang perlu diupdate.
    """
    try:
        text = material_to_text(material)
        return {"status": "success", "text": text}
    except Exception as exc:
        logger.error("material-to-text error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

#Endpoint utama untuk evaluasi RAGAS — menerima question, context, answer, ground_truth (opsional)
@router.post(
    "/ragas",
    response_model=EvaluationResponse,
    summary="Evaluasi RAG menggunakan RAGAS",
    description="""
    Mengevaluasi kualitas jawaban RAG menggunakan framework RAGAS.
    
    **Metrik yang dievaluasi:**
    - **Faithfulness**: Seberapa faktual jawaban berdasarkan konteks yang diberikan (0.0 - 1.0)
    - **Answer Relevancy**: Seberapa relevan jawaban terhadap pertanyaan user (0.0 - 1.0)
    - **Overall Score**: Rata-rata dari semua metrik yang tersedia
    
    **Metrik tambahan jika `ground_truth` diisi:**
    - **Context Precision**: seberapa presisi konteks yang di-retrieve vs ground truth (0–1)
    - **Context Recall**: seberapa lengkap konteks mencakup ground truth (0–1)

    **Interpretasi skor:**
    - Sangat Baik  : >= 0.8
    - Cukup Baik   : 0.6 - 0.79
    - Perlu Perbaikan : < 0.6
    """,
)

async def evaluate_ragas(
    payload: EvaluationRequest,
    db: Session = Depends(get_db),
):
    """
    Endpoint untuk menjalankan evaluasi RAGAS terhadap satu sample RAG.
    Mendelegasikan ke evaluator service (port 8001) via HTTP POST.
    """
    try:
        # Langsung kirim payload apa adanya ke evaluator 
        async with httpx.AsyncClient(timeout=EVALUATOR_TIMEOUT) as client:
            response = await client.post(
                EVALUATOR_ENDPOINT,
                json={
                    "question": payload.question,
                    "context": payload.context,
                    "answer": payload.answer,
                    "ground_truth": payload.ground_truth,
                    "source_label": "manual_evaluation",
                },
            )
            response.raise_for_status()
            result = response.json()

    except httpx.ConnectError:
        logger.error("Evaluator service tidak dapat dijangkau: %s", EVALUATOR_ENDPOINT)
        raise HTTPException(
            status_code=503,
            detail="Evaluator service tidak dapat dijangkau. Pastikan container evaluator berjalan.",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail=f"Evaluator service timeout setelah {EVALUATOR_TIMEOUT}s.",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Evaluator service mengembalikan error: {exc.response.text}",
        )

    if result.get("status") == "error":
        raise HTTPException(
            status_code=500,
            detail=f"Evaluasi RAGAS gagal: {result.get('error')}",
        )

    if payload.history_id is not None:
        updated = RAGHistoryService.update_ragas(
            db=db,
            history_id=payload.history_id,
            ragas_result=result,
        )
        if not updated:
            logger.warning(
                "Gagal update ragas_metrics untuk history_id=%s setelah evaluasi manual",
                payload.history_id,
            )

    return result