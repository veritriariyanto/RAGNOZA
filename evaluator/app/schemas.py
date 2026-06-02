"""
evaluator/app/schemas.py

Schema Pydantic untuk request dan response endpoint /evaluate.
Dipisah dari schema service utama agar tidak ada shared dependency.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class EvaluationRequest(BaseModel):
    question: str = Field(..., description="Pertanyaan asli dari user")
    context: str = Field(..., description="Context yang di-retrieve dari Qdrant")
    answer: str = Field(..., description="Jawaban final dari LLM")
    ground_truth: Optional[str] = Field(
        None,
        description="Ground truth opsional. Jika None, context digunakan sebagai proxy.",
    )
    source_label: str = Field(
        "rag_pipeline",
        description="Label sumber untuk keperluan logging",
    )


class EvaluationMetrics(BaseModel):
    faithfulness: Optional[float] = None
    answer_relevancy: Optional[float] = None
    context_precision: Optional[float] = None
    context_recall: Optional[float] = None
    overall_score: Optional[float] = None


class EvaluationResponse(BaseModel):
    status: str
    metrics: Optional[EvaluationMetrics] = None
    error: Optional[str] = None
    input: Optional[dict] = None
    timestamp: str = Field(             
        default_factory=lambda: datetime.now().strftime("%H:%M:%S")
    )