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


class TextIntegrationRequest(BaseModel):
    """Request body for text-based pipeline (transcription already done)."""
    text: str = Field(..., description="Raw transcription text to process")
    knowledge_base: str = Field(
        "uud_1945", description="Qdrant collection name")
    style: str = Field(
        "formal", description="Writing style: formal/casual/academic")
    auto_evaluate: bool = Field(
        True, description="Run RAGAS evaluation in background")
    session_id: Optional[int] = Field(None, description="Existing session ID")
