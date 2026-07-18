# app/schemas/evaluation/evaluation_dataset.py

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


# ── Dataset ──────────────────────────────────────────────────────────────

class EvaluationDatasetCreate(BaseModel):
    name: str
    description: Optional[str] = None


class EvaluationDatasetResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    total_items: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


# ── Dataset Item ─────────────────────────────────────────────────────────

class EvaluationDatasetItemCreate(BaseModel):
    question: str = Field(..., description="Skenario/pertanyaan hukum kurasi")
    ground_truth: str = Field(..., description="Jawaban rujukan")
    reference_context: str = Field(..., description="Context/pasal rujukan manual yang dikunci")
    category: Optional[str] = Field(default=None, description="Kategori/tag soal")
    knowledge_base: str = Field(..., description="Nama collection Qdrant tempat soal ini berasal (wajib diisi)")


class EvaluationDatasetItemBulkCreate(BaseModel):
    items: List[EvaluationDatasetItemCreate]


class EvaluationDatasetItemResponse(BaseModel):
    id: int
    dataset_id: int
    question: str
    ground_truth: str
    reference_context: str
    category: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Run ──────────────────────────────────────────────────────────────────

class EvaluationRunTriggerRequest(BaseModel):
    label: Optional[str] = Field(default=None, description="Label run, mis. 'baseline', 'prompt-v2'")


class EvaluationRunResponse(BaseModel):
    id: int
    dataset_id: int
    label: Optional[str] = None
    status: str
    triggered_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EvaluationRunItemDetail(BaseModel):
    dataset_item_id: int
    question: str
    category: Optional[str] = None
    process_id: Optional[int] = None
    evaluation_type: str
    faithfulness_summary: Optional[float] = None
    faithfulness_qa: Optional[float] = None
    answer_relevancy: Optional[float] = None
    context_precision: Optional[float] = None
    context_recall: Optional[float] = None
    risk_faithfulness: Optional[float] = None


class EvaluationRunReportResponse(BaseModel):
    run_id: int
    dataset_id: int
    label: Optional[str] = None
    status: str
    total_items: int
    aggregate_live: dict
    aggregate_reference: dict
    aggregate_by_category: dict
    items: List[EvaluationRunItemDetail]

# ── CSV Upload ───────────────────────────────────────────────────────────────

class CsvUploadRowError(BaseModel):
    row_number: int
    reason: str


class CsvUploadResult(BaseModel):
    dataset_id: int
    inserted_count: int
    skipped_count: int
    errors: List[CsvUploadRowError]