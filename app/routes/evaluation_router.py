# app/routes/evaluation_router.py

from fastapi import APIRouter, HTTPException

from app.schemas.evaluation import EvaluationRequest, EvaluationResponse
from app.services.evaluation_service import EvaluationService

router = APIRouter(prefix="/evaluation", tags=["Evaluation"])

evaluation_service = EvaluationService()

@router.post(
    "/ragas",
    response_model=EvaluationResponse,
    summary="Evaluasi RAG menggunakan RAGAS",
    description=""""
    Mengevaluasi kualitas jawaban RAG menggunakan framework RAGAS.
    
    **Metrik yang dievaluasi:**
    - **Faithfulness**: Seberapa faktual jawaban berdasarkan konteks yang diberikan (0.0 - 1.0)
    - **Answer Relevancy**: Seberapa relevan jawaban terhadap pertanyaan user (0.0 - 1.0)
    - **Overall Score**: Rata-rata dari semua metrik yang tersedia
    
    **Metrik tambahan jika `ground_truth` diisi:**
    - **Context Precision**: seberapa presisi konteks yang di-retrieve vs ground truth (0–1)
    - **Context Recall**: seberapa lengkap konteks mencakup ground truth (0–1)

    **Interpretasi skor:**
    - 🟢 ≥ 0.8 : Sangat Baik
    - 🟡 0.6 - 0.79 : Cukup Baik  
    - 🔴 < 0.6 : Perlu Perbaikan
    """,
)

async def evaluate_ragas(payload: EvaluationRequest):
    """
    Endpoint untuk menjalankan evaluasi RAGAS terhadap satu sample RAG.
    
    - **question**: Pertanyaan yang diajukan user
    - **context**: Konteks yang di-retrieve dari knowledge base (gabungan chunk)
    - **answer**: Jawaban yang dihasilkan LLM
    - **ground_truth**: Jawaban kebenaran (jika tersedia)
    """

    result = await evaluation_service.run_evaluation(
        question=payload.question,
        context=payload.context,
        answer=payload.answer,
        ground_truth=payload.ground_truth,
    )

    if result["status"] == "error":
        raise HTTPException(
            status_code=500, 
            detail=f"Evaluasi RAGAS gagal: {result['error']}",
        )

    return result


