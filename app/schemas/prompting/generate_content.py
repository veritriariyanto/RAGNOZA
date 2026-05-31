# app/schemas/prompting/generate_content.py

from typing import List, Optional

from pydantic import BaseModel, Field

class MaterialRequest(BaseModel):
    context_text: str = Field(..., description="Dokumen UU atau aturan hukum terkait (dari hasil retrieval RAG)")
    user_scenario: str = Field(..., description="Kasus nyata atau rencana tindakan yang ingin dievaluasi oleh pengguna")


class SummaryBlock(BaseModel):
    title: str = Field(default="Summary", description="Judul blok ringkasan")
    overview: str = Field(..., description="Ringkasan isi dokumen hukum secara singkat dan mudah dipahami")
    key_points: List[str] = Field(default_factory=list, description="Poin-poin penting dari dokumen atau skenario")
    conclusion: str = Field(..., description="Kesimpulan singkat dari analisis")


class ClauseSearchItem(BaseModel):
    clause_topic: str = Field(..., description="Topik atau kata kunci pasal yang dicari")
    source_name: str = Field(..., description="Nama undang-undang atau peraturan sumber")
    article: str = Field(..., description="Nomor pasal, ayat, atau klausul yang relevan")
    excerpt: Optional[str] = Field(default=None, description="Cuplikan teks otentik jika tersedia di konteks")
    relevance: str = Field(..., description="Mengapa klausul ini relevan terhadap skenario")


class LegalQAItem(BaseModel):
    question: str = Field(..., description="Pertanyaan pengguna dalam format tanya jawab")
    answer: str = Field(..., description="Jawaban ringkas, jelas, dan berbasis konteks hukum")


class RiskReviewBlock(BaseModel):
    status: str = Field(..., description="Status kepatuhan atau risiko keseluruhan")
    score: int = Field(..., description="Skor kepatuhan atau risiko dari skala 1-100")
    analysis: str = Field(..., description="Analisis potensi risiko, kelemahan klausul, atau dampak sengketa")
    risks: List[str] = Field(default_factory=list, description="Daftar risiko hukum atau celah yang ditemukan")
    mitigation_steps: List[str] = Field(default_factory=list, description="Langkah mitigasi yang disarankan")
    recommendation: str = Field(..., description="Rekomendasi tindakan konkret dan solutif")


class TimelineItem(BaseModel):
    date_or_period: str = Field(..., description="Tanggal, masa berlaku, tenggat, atau urutan peristiwa")
    event: str = Field(..., description="Peristiwa atau kewajiban hukum yang terkait")
    relevance: str = Field(..., description="Kaitan waktu tersebut dengan analisis hukum")


class ComparisonItem(BaseModel):
    aspect: str = Field(..., description="Aspek yang dibandingkan")
    source_a: str = Field(..., description="Ketentuan, pasal, atau dokumen pertama")
    source_b: str = Field(..., description="Ketentuan, pasal, atau dokumen kedua")
    similarities: List[str] = Field(default_factory=list, description="Persamaan yang ditemukan")
    differences: List[str] = Field(default_factory=list, description="Perbedaan yang ditemukan")
    conclusion: str = Field(..., description="Kesimpulan perbandingan")


class LegalReferenceItem(BaseModel):
    source_name: str = Field(..., description="Nama undang-undang atau peraturan yang dirujuk")
    article: str = Field(..., description="Nomor pasal atau ayat yang relevan")
    excerpt: Optional[str] = Field(default=None, description="Cuplikan teks pasal bila tersedia dari konteks")
    relevance: str = Field(..., description="Penjelasan singkat relevansi pasal terhadap skenario")


class MaterialResponse(BaseModel):
    summary: SummaryBlock = Field(..., description="Blok summary")
    clause_search: List[ClauseSearchItem] = Field(default_factory=list, description="Blok clause search")
    legal_qa: List[LegalQAItem] = Field(default_factory=list, description="Blok legal Q&A")
    risk_review: RiskReviewBlock = Field(..., description="Blok risk review")
    timeline_extraction: List[TimelineItem] = Field(default_factory=list, description="Blok timeline extraction")
    comparison: List[ComparisonItem] = Field(default_factory=list, description="Blok comparison")
    referensi_uu: List[LegalReferenceItem] = Field(default_factory=list, description="Referensi UU otentik")

    @property
    def decision_status(self) -> str:
        return self.risk_review.status

    @property
    def compliance_score(self) -> int:
        return self.risk_review.score

    @property
    def recommendation(self) -> str:
        return self.risk_review.recommendation

    @property
    def risk_analysis(self) -> List[str]:
        return self.risk_review.risks

    @property
    def legal_basis(self) -> List[str]:
        return [f"{item.source_name} Pasal {item.article}" for item in self.referensi_uu]

    @property
    def resume(self) -> SummaryBlock:
        return self.summary

    @property
    def faq(self) -> List[LegalQAItem]:
        return self.legal_qa

    @property
    def kepatuhan_regulasi(self) -> RiskReviewBlock:
        return self.risk_review