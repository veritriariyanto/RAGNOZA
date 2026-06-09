# app/schemas/evaluasi/evaluation_schemas.py
#

from pydantic import BaseModel, Field
from typing import Optional, List, Any

# =============================================================================
# REQUEST SCHEMAS (Data yang Masuk dari Frontend ke Backend)
# =============================================================================

# Model/Schema ini digunakan pada router / ragas-auto-2metriks
class MaterialEvaluationRequest(BaseModel):
    """
    Skema data untuk Request Body endpoint Path A: `/evaluation/ragas-auto-2metriks`.
    Digunakan saat Frontend Streamlit meminta evaluasi otomatis pertama kali 
    tepat setelah AI selesai men-generate materi dokumen hukum.
    """
    question: str = Field(..., description="Pertanyaan user")
    context: str = Field(..., description="Konteks dokumen dari RAG pipeline")
    material: Any = Field(..., description="MaterialResponse.model_dump() — dict hasil generate")
    ground_truth: Optional[str] = Field(None, description="Jawaban ideal dari legal expert")
    history_id: Optional[int] = Field(None, description="ID history untuk update DB")
    source_label: Optional[str] = Field("frontend_eval", description="Label asal request")

# Model/Schema ini digunakan pada router / ragas-auto-2metriks
class ReevalRequest(BaseModel):
    """
    Skema data untuk Request Body endpoint Path B: `/evaluation/ragas-ground-truth`.
    Digunakan ketika user memasukkan kunci jawaban ideal (ground_truth) secara manual 
    pada aplikasi Streamlit untuk melakukan hitung ulang metrik presisi dan recall.
    """
    history_id: int = Field(..., description="ID history yang ingin di-re-evaluasi")
    ground_truth: str = Field(..., description="Jawaban ideal dari user/legal expert")
    question: Optional[str] = Field(None, description="Override pertanyaan (opsional, diambil dari DB jika kosong)")
    context: Optional[str] = Field(None, description="Override konteks (opsional, diambil dari DB jika kosong)")

# Model/Schema hasil evaluasi 
class EvaluationMetrics(BaseModel):
    """
    Struktur data untuk menampung seluruh skor angka hasil evaluasi RAGAS.
    Semua skor menggunakan tipe 'Optional[float]' (angka desimal 0.0 - 1.0) 
    karena tidak semua metrik akan dihitung secara bersamaan (tergantung endpoint mana yang dipanggil).

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

    # BARU (FIX #2): Metrik krusial untuk domain hukum guna mendeteksi halusinasi pada analisis risiko
    risk_faithfulness: Optional[float] = Field(
        None,
        description=(
            "Faithfulness segmen Risk Review — apakah klaim status hukum, "
            "analisis, dan rekomendasi berbasis konteks dokumen? (0–1). "
            "Metrik paling penting untuk mencegah hallucination pada output hukum."
        ),
    )

    # Metadata Skor Akhir & Cakupan Fitur
    overall_score: Optional[float] = Field(
        None, description="Rata-rata semua metrik yang tersedia (berdasarkan bobot)"
    )
    # default_factory=list digunakan agar jika datanya kosong, otomatis terbuat array kosong [] bukan None
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
    """
    Skema data internal untuk membungkus kembali teks input asli 
    yang dikirimkan ke mesin Evaluator (sebagai rekaman/log audit data input).
    """
    question: str
    context: str
    answer: str
    ground_truth: Optional[str] = None
    answer_qa: Optional[str] = None      # ← tambah ini
    source_label: Optional[str] = None 

# =============================================================================
# RESPONSE SCHEMA (Format Data yang Keluar/Dikembalikan ke Frontend)
# =============================================================================

class EvaluationResponse(BaseModel):
    """
    Skema respons akhir yang akan diterima oleh Frontend Streamlit.
    Menyediakan format yang konsisten: status sukses/gagal, metrik skor, data input balik, dan detail error.
    """
    status: str
    metrics: Optional[EvaluationMetrics] = None
    input: EvaluationInput
    error: Optional[str] = None