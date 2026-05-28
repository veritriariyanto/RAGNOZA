# app/schemas/evaluasi/evaluation.py

from pydantic import BaseModel, Field
from typing import Optional

class EvaluationRequest(BaseModel):
    """Request body untuk endpoint evaluasi RAGAS."""
    question: str = Field(
        ...,
        description="Pertanyaan yang diajukan user ke sistem RAG",
        examples=["Apa bunyi Pasal 1 UUD 1945?"]
    )
    context: str = Field(
        ...,
        description="Konteks yang di-retrieve dari knowledge base untuk menjawab pertanyaan",
        examples=["Negara Indonesia ialah Negara Kesatuan yang berbentuk Republik."]
    )
    answer: str = Field(
        ...,
        description="Jawaban yang dihasilkan oleh LLM berdasarkan pertanyaan dan konteks",
        examples=["Pasal 1 UUD 1945 menyatakan bahwa Negara Indonesia ialah Negara Kesatuan yang berbentuk Republik."]
    )
    ground_truth: Optional[str] = Field(
        None,
        description="Jawaban kebenaran (ground truth) yang ideal untuk pertanyaan tersebut, jika tersedia. Berguna untuk evaluasi yang lebih mendalam.",
    )

class EvaluationMetrics(BaseModel):
    """Hasil metrik dari evaluasi RAGAS."""
    faithfulness: Optional[float] = Field(
        None,
        description="Seberapa faktual jawaban berdasarkan konteks yang diberikan (0.0 - 1.0)",
    )
    answer_relevancy: Optional[float] = Field(
        None,
        description="Seberapa relevan jawaban terhadap pertanyaan yang diajukan (0.0 - 1.0)",
    )
    context_precision: Optional[float] = Field(
        None,
        description="Presisi konteks vs ground truth (0–1)",
    )
    context_recall: Optional[float] = Field(
        None,
        description="Recall konteks vs ground truth (0–1)",
    )

    overall_score: Optional[float] = Field(
        None,
        description="Rata-rata semua metrik yang tersedia (0.0 - 1.0)"
    )

class EvaluationInput(BaseModel):
    """Input lengkap untuk evaluasi, termasuk pertanyaan, konteks, dan jawaban."""
    question: str
    context: str
    answer: str
    ground_truth: Optional[str] = None

class EvaluationResponse(BaseModel):
    """Response body dari endpoint evaluasi RAGAS."""

    status: str = Field(
        ...,
        description="'success' atau 'error'"
    )
    metrics: Optional[EvaluationMetrics] = Field(
        None
    )
    input: EvaluationInput
    error: Optional[str] = Field(
        None,
        description="Pesan error jika status = 'error'"
    )