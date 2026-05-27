#app/schemas/prompting/generate_content.py

from pydantic import BaseModel, Field
from typing import List

class MaterialRequest(BaseModel):
    context_text: str = Field(..., description="Dokumen UU atau aturan hukum terkait (dari hasil retrieval RAG)")
    user_scenario: str = Field(..., description="Kasus nyata atau rencana tindakan yang ingin dievaluasi oleh pengguna")

class MaterialResponse(BaseModel):
    decision_status: str = Field(..., description="Status keputusan final, contoh: 'DILEGALKAN', 'DILARANG', 'MEMERLUKAN IZIN KHUSUS'")
    compliance_score: int = Field(..., description="Skor kepatuhan hukum dari skala 1-100")
    recommendation: str = Field(..., description="Rekomendasi tindakan konkret dan solutif dalam format Markdown")
    risk_analysis: List[str] = Field(..., description="Daftar potensi risiko hukum, sanksi, atau denda jika skenario dijalankan")
    legal_basis: List[str] = Field(..., description="Daftar pasal atau peraturan perundang-undangan spesifik yang dirujuk")