# app/schemas/prompting/integration.py

from pydantic import BaseModel, Field
from typing import List, Optional, Any
from app.schemas.prompting.generate_content import MaterialResponse


class RAGIntegrationResponse(BaseModel):
    raw_transcribe: str
    final_repaired_text: str
    user_scenario: str
    search_query_used: str
    retrieved_context: str
    source_details: List[Any]
    history_id: Optional[int] = None
    session_id: Optional[int] = None
    # Tambahkan field untuk hasil akhir generate material
    final_material: Optional[MaterialResponse] = None
    fallback_message: Optional[str] = None
    has_context: bool
    # FIX: evaluasi RAGAS sekarang synchronous (ditunggu sampai selesai sebelum
    # response dikirim), bukan lagi background task murni — hasil dibawa langsung
    # di sini agar frontend tidak perlu polling/refresh terpisah.
    ragas_status: Optional[str] = None       # "success" | "error" | "skipped" | None (jika auto_evaluate=False)
    ragas_metrics: Optional[dict] = None      # EvaluationMetrics.model_dump() jika sukses
    ragas_error: Optional[str] = None


# Sinkron dengan TEXT_INPUT_MAX_CHARS di streamlit_app/components/audio_controls.py.
# Batas dipilih berdasarkan token budget generate_legal_material (system_prompt +
# build_output_instructions + format_instructions ≈ 3000 token fixed dari 6000 TPM
# Groq free tier) — lihat rag_integration_service.py.
TEXT_INPUT_MAX_CHARS = 1000


class TextIntegrationRequest(BaseModel):
    """Request body for text-based pipeline (transcription already done)."""
    text: str = Field(
        ..., min_length=1, max_length=TEXT_INPUT_MAX_CHARS,
        description="Raw transcription text to process",
    )
    knowledge_base: str = Field(
        "uud_1945", description="Qdrant collection name")
    style: str = Field(
        "formal", description="Writing style: formal/casual/academic")
    auto_evaluate: bool = Field(
        True, description="Run RAGAS evaluation in background")
    session_id: Optional[int] = Field(None, description="Existing session ID")
    stt_provider: Optional[str] = Field(
        None,
        description="Provider STT yang menghasilkan teks ini ('whisper'/'elevenlabs'), "
                    "jika teks berasal dari transkripsi audio. None jika teks diketik manual.",
    )
