# evaluator/app/schemas/evaluation_schemas.py
#
# FIX #3: tambah is_reeval + existing_* fields di EvaluationRequest
# agar evaluator tahu kapan harus skip faithfulness/relevancy/risk.

from pydantic import BaseModel, Field
from typing import Optional, List


class EvaluationRequest(BaseModel):
    """
    Request dari service utama (port 8000) ke evaluator (port 8001).

    FIX #3 — field baru:
        is_reeval         : True = user baru input ground_truth, hitung precision+recall saja
        existing_*        : skor dari auto eval sebelumnya untuk di-merge
    """
    question: str
    context: str
    faithfulness_text: str
    answer_qa: str
    answer_risk: str
    answer: str
    ground_truth: Optional[str] = None
    history_id: Optional[int] = None
    source_label: Optional[str] = "rag_pipeline"
    context_chunks: Optional[List[str]] = Field(
    default=None,
    description="Actual retrieved chunks dari RAG pipeline untuk context_precision dan context_recall"
)

    # FIX #3 — re-evaluasi efisien
    is_reeval: bool = Field(
        default=False,
        description=(
            "True jika ini adalah re-evaluasi setelah user input ground_truth. "
            "Jika True, hanya context_precision dan context_recall yang dihitung. "
            "faithfulness/relevancy/risk_faithfulness diambil dari existing_* fields."
        ),
    )
    existing_faithfulness: Optional[float] = Field(
        None, description="Skor faithfulness dari auto eval sebelumnya"
    )
    existing_answer_relevancy: Optional[float] = Field(
        None, description="Skor answer_relevancy dari auto eval sebelumnya"
    )
    existing_risk_faithfulness: Optional[float] = Field(
        None, description="Skor risk_faithfulness dari auto eval sebelumnya"
    )
    existing_overall: Optional[float] = Field(
        None, description="Overall Quality Score (Weighted) dari auto eval sebelumnya (akan dihitung ulang)"
    )
    existing_segments: Optional[List[str]] = Field(
        default_factory=list,
        description="Segmen yang sudah dievaluasi di auto eval, misal: ['summary','qa','risk']",
    )


class EvaluationMetrics(BaseModel):
    faithfulness: Optional[float] = None
    answer_relevancy: Optional[float] = None
    context_precision: Optional[float] = None
    context_recall: Optional[float] = None
    risk_faithfulness: Optional[float] = None
    answer_faithfulness_segment: List[str] = Field(default_factory=list)


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