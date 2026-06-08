#app/schemas/prompting/integration.py

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
    # Tambahkan field untuk hasil akhir generate material
    final_material: Optional[MaterialResponse] = None
    fallback_message: Optional[str] = None
    has_context: bool
    session_id: Optional[int] = None
    