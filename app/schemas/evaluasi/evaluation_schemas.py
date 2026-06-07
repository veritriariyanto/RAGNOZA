# app/schemas/evaluasi/evaluation_schemas.py
#

from pydantic import BaseModel, Field
from typing import Optional, List, Any

# Model/Schema ini digunakan pada router / ragas-auto-2metriks
class MaterialEvaluationRequest(BaseModel):
    """
    Request body untuk endpoint BARU /evaluation/ragas-auto-2metriks.

    Menerima MaterialResponse sebagai dict — backend melakukan ekstraksi segmen.
    Ini adalah cara yang benar untuk evaluasi dari Streamlit frontend.
    """
    question: str = Field(..., description="Pertanyaan user")
    context: str = Field(..., description="Konteks dokumen dari RAG pipeline")
    material: Any = Field(..., description="MaterialResponse.model_dump() — dict hasil generate")
    ground_truth: Optional[str] = Field(None, description="Jawaban ideal dari legal expert")
    history_id: Optional[int] = Field(None, description="ID history untuk update DB")
    source_label: Optional[str] = Field("frontend_eval", description="Label asal request")

# Model/Schema ini digunakan pada router / ragas-auto-2metriks
class ReevalRequest(BaseModel):
    """Request body untuk endpoint /evaluation/ragas-ground-truth."""
    history_id: int = Field(..., description="ID history yang ingin di-re-evaluasi")
    ground_truth: str = Field(..., description="Jawaban ideal dari user/legal expert")
    question: Optional[str] = Field(None, description="Override pertanyaan (opsional, diambil dari DB jika kosong)")
    context: Optional[str] = Field(None, description="Override konteks (opsional, diambil dari DB jika kosong)")

# Model/Schema hasil evaluasi 
class EvaluationMetrics(BaseModel):
    """
    Hasil metrik dari evaluasi RAGAS tersegmentasi.

    PERUBAHAN:
        + risk_faithfulness   : faithfulness khusus segmen Risk Review (FIX #2)
        + answer_faithfulness_segment  : daftar segmen yang benar-benar dievaluasi
        + coverage_pct        : persentase fitur yang dievaluasi (dari 7 fitur total)
    """
    # Metrik existing
    faithfulness: Optional[float] = Field(
        None, description="Faithfulness segmen Summary — klaim berbasis konteks? (0–1)"
    )
    answer_relevancy: Optional[float] = Field(
        None, description="Relevancy segmen QA & Search — relevan ke pertanyaan? (0–1)"
    )
    context_precision: Optional[float] = Field(
        None, description="Presisi retrieval vs ground truth (0–1, butuh ground_truth)"
    )
    context_recall: Optional[float] = Field(
        None, description="Recall retrieval vs ground truth (0–1, butuh ground_truth)"
    )

    # BARU: metrik untuk segmen Risk (FIX #2)
    risk_faithfulness: Optional[float] = Field(
        None,
        description=(
            "Faithfulness segmen Risk Review — apakah klaim status hukum, "
            "analisis, dan rekomendasi berbasis konteks dokumen? (0–1). "
            "Metrik paling penting untuk mencegah hallucination pada output hukum."
        ),
    )

    # BARU: metadata coverage
    overall_score: Optional[float] = Field(
        None, description="Rata-rata semua metrik yang tersedia"
    )
    answer_faithfulness_segment: List[str] = Field(
        default_factory=list,
        description="Segmen yang dievaluasi, misal: ['summary', 'qa', 'risk']",
    )
    coverage_pct: Optional[float] = Field(
        None,
        description=(
            "Persentase fitur yang dievaluasi dari 7 fitur total "
            "(Summary, ClauseSearch, LegalQA, RiskReview, Timeline, Comparison, Referensi). "
            "Nilai 1.0 = semua fitur dievaluasi."
        ),
    )


class EvaluationInput(BaseModel):
    question: str
    context: str
    answer: str
    ground_truth: Optional[str] = None
    answer_qa: Optional[str] = None      # ← tambah ini
    source_label: Optional[str] = None 


class EvaluationResponse(BaseModel):
    status: str
    metrics: Optional[EvaluationMetrics] = None
    input: EvaluationInput
    error: Optional[str] = None