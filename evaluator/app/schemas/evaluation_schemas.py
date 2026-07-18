# evaluator/app/schemas/evaluation_schemas.py
#
# FIX #3: tambah is_reeval + existing_* fields di EvaluationRequest
# agar evaluator tahu kapan harus skip faithfulness/relevancy/risk.
#
# FIX #8 (efisiensi token dataset_eval_reference): tambah skip_answer_relevancy.
# Berbeda dengan is_reeval (yang skip faithfulness+relevancy+risk sekaligus,
# hanya hitung precision+recall), skip_answer_relevancy HANYA melewati
# answer_relevancy saja — faithfulness_summary/qa/risk/precision/recall
# tetap dihitung ulang seperti biasa. Dipakai khusus oleh dataset_eval_reference:
# pertanyaan & jawaban identik dengan dataset_eval_live (context beda), dan
# answer_relevancy secara definisi tidak bergantung pada context sama sekali
# — menghitungnya ulang hanya membuang ~3 LLM call/soal tanpa nilai tambah.

from pydantic import BaseModel, Field
from typing import Optional, List


class EvaluationRequest(BaseModel):
    """
    Request dari service utama (port 8000) ke evaluator (port 8001).

    FIX #3 — field baru:
        is_reeval         : True = user baru input ground_truth, hitung precision+recall saja
        existing_*        : skor dari auto eval sebelumnya untuk di-merge

    FIX #8 — field baru:
        skip_answer_relevancy : True = jangan hitung ulang answer_relevancy,
                                 pakai existing_answer_relevancy sebagai gantinya.
                                 Faithfulness/precision/recall/risk TETAP dihitung
                                 (beda dengan is_reeval).
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
    existing_faithfulness: Optional[float] = Field(None, description="Skor faithfulness dari auto eval sebelumnya")
    existing_answer_relevancy: Optional[float] = Field(None, description="Skor answer_relevancy dari auto eval sebelumnya")
    existing_risk_faithfulness: Optional[float] = Field(None, description="Skor risk_faithfulness dari auto eval sebelumnya")
    existing_overall: Optional[float] = Field(None, description="Overall Quality Score (Weighted) dari auto eval sebelumnya (akan dihitung ulang)")
    existing_segments: Optional[List[str]] = Field(
        default_factory=list,
        description="Segmen yang sudah dievaluasi di auto eval, misal: ['summary','qa','risk']",
    )
    # FIX #7 (Prioritas 4)
    existing_faithfulness_summary: Optional[float] = Field(
        None, description="Skor faithfulness segmen Summary dari auto eval sebelumnya"
    )
    existing_faithfulness_qa: Optional[float] = Field(
        None, description="Skor faithfulness segmen QA dari auto eval sebelumnya"
    )

    # FIX #8 — skip answer_relevancy saja (granular, beda dengan is_reeval)
    skip_answer_relevancy: bool = Field(
        default=False,
        description=(
            "True jika answer_relevancy tidak perlu dihitung ulang — dipakai saat "
            "question & answer identik dengan evaluasi sebelumnya dan hanya context "
            "yang berubah (mis. dataset_eval_reference vs dataset_eval_live). "
            "answer_relevancy tidak bergantung pada context sama sekali, jadi hasil "
            "akan selalu identik — menghitung ulang hanya boros token. Nilai "
            "existing_answer_relevancy dipakai sebagai pengganti. Metrik lain "
            "(faithfulness_summary/qa, risk_faithfulness, precision, recall) TETAP "
            "dihitung penuh seperti biasa."
        ),
    )


class EvaluationMetrics(BaseModel):
    faithfulness: Optional[float] = None
    answer_relevancy: Optional[float] = None
    context_precision: Optional[float] = None
    context_recall: Optional[float] = None
    risk_faithfulness: Optional[float] = None
    answer_faithfulness_segment: List[str] = Field(default_factory=list)

    # FIX #7 (Prioritas 4): skor per-segmen, agar "faithfulness" gabungan tidak menyembunyikan
    # segmen mana yang sebenarnya bermasalah. Field "faithfulness" di atas dipertahankan
    # di schema untuk backward compatibility, TAPI SEJAK FIX #Fase0-1 SUDAH TIDAK DIISI
    # (selalu None dari full eval) — bukan lagi rata-rata summary+qa. Sumber kebenaran
    # sekarang adalah faithfulness_summary dan faithfulness_qa di bawah ini.
    faithfulness_summary: Optional[float] = Field(
        None, description="Faithfulness khusus segmen Summary saja (0–1)"
    )
    faithfulness_qa: Optional[float] = Field(
        None, description="Faithfulness khusus segmen QA saja (0–1)"
    )


class EvaluationInput(BaseModel):
    question: str
    context: str
    answer: str
    ground_truth: Optional[str] = None
    answer_qa: Optional[str] = None      # ← tambah ini
    source_label: Optional[str] = None
    # FIX #Fase0-2 (M13): teks segmen faithfulness & risk agar tersimpan ke DB
    faithfulness_text: Optional[str] = None
    answer_risk: Optional[str] = None


class EvaluationResponse(BaseModel):
    status: str
    metrics: Optional[EvaluationMetrics] = None
    input: EvaluationInput
    error: Optional[str] = None