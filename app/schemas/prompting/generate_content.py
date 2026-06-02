from typing import List, Optional
from pydantic import BaseModel, Field

class MaterialRequest(BaseModel):
    context_text: str = Field(..., description="Dokumen UU atau aturan hukum terkait (dari hasil retrieval RAG)")
    user_scenario: str = Field(..., description="Kasus nyata atau rencana tindakan yang ingin dievaluasi oleh pengguna")


class SummaryBlock(BaseModel):
    title: str = Field(default="Summary", description="Judul blok ringkasan")
    overview: str = Field(..., description="Ringkasan isi dokumen hukum secara singkat, presisi, dan murni berbasis konteks yang disediakan")
    key_points: List[str] = Field(default_factory=list, description="Poin-poin penting fakta hukum yang tercantum dalam dokumen")
    conclusion: str = Field(..., description="Kesimpulan singkat dari analisis hubungan antara skenario dan dokumen hukum")


class ClauseSearchItem(BaseModel):
    clause_topic: str = Field(..., description="Topik atau kata kunci klausul/pasal yang dicari")
    source_name: str = Field(..., description="Nama resmi undang-undang atau peraturan peraturan (CONTOH: 'UU Nomor 1 Tahun 2024 tentang ITE'). DILARANG MENYIMPULKAN JIKA TIDAK ADA DI TEKS.")
    article: str = Field(..., description="Nomor pasal, ayat, atau klausul spesifik yang relevan (CONTOH: 'Pasal 27A ayat (5)')")
    excerpt: Optional[str] = Field(default=None, description="Salinan teks otentik/asli dari pasal tersebut yang diambil langsung dari konteks tanpa diubah sedikit pun")
    relevance: str = Field(..., description="Penjelasan objektif mengapa klausul ini relevan terhadap skenario tindakan pengguna")


class LegalQAItem(BaseModel):
    question: str = Field(..., description="Pertanyaan kritis terkait skenario kasus pengguna")
    answer: str = Field(..., description="Jawaban tegas, ringkas, dan 100% berbasis fakta hukum pada konteks (katakan tidak tahu jika tidak tertulis di teks)")


class RiskReviewBlock(BaseModel):
    status: str = Field(..., description="Status kepatuhan/risiko hukum skenario pengguna (CONTOH: 'Risiko Tinggi', 'Patuh', 'Ilegal')")
    score: int = Field(..., description="Skor tingkat kepatuhan hukum pengguna dengan skala nilai 1-100 (100 berarti sangat patuh/aman, 1 berarti risiko hukum sangat fatal)")
    analysis: str = Field(..., description="Analisis mendalam mengenai potensi risiko, celah hukum, atau dampak tuntutan/sengketa dari skenario")
    risks: List[str] = Field(default_factory=list, description="Daftar risiko hukum spesifik atau ancaman sanksi pidana/perdata yang mengintai pengguna")
    mitigation_steps: List[str] = Field(default_factory=list, description="Langkah konkret, taktis, dan solutif yang wajib dilakukan pengguna untuk menghindari atau menurunkan risiko hukum tersebut")
    recommendation: str = Field(..., description="Rekomendasi tindakan akhir yang konkret bagi pengguna (CONTOH: 'Batalkan tindakan', 'Lanjutkan dengan syarat x')")


class TimelineItem(BaseModel):
    date_or_period: str = Field(..., description="Elemen waktu eksplisit dari dokumen seperti tanggal, batas waktu pengaduan, durasi masa hukuman, atau masa berlaku (CONTOH: '2 Tahun', 'Batas 6 Bulan'). JANGAN DIISI NAMA PASAL.")
    event: str = Field(..., description="Peristiwa hukum, tenggat waktu, atau kewajiban yang berkaitan dengan elemen waktu tersebut")
    relevance: str = Field(..., description="Penjelasan kaitan waktu tersebut dengan kasus hukum atau skenario pengguna")


class ComparisonItem(BaseModel):
    aspect: str = Field(..., description="Aspek hukum yang diperbandingkan")
    source_a: str = Field(..., description="Ketentuan, pasal, atau dokumen pertama yang menjadi pembanding utama")
    source_b: str = Field(..., description="Ketentuan, pasal, atau dokumen kedua yang ada di dalam teks sebagai elemen pembanding alternatif")
    similarities: List[str] = Field(default_factory=list, description="Persamaan substansi hukum yang ditemukan dari kedua pasal/ketentuan tersebut")
    differences: List[str] = Field(default_factory=list, description="Perbedaan hak, kewajiban, atau sanksi dari kedua pasal tersebut")
    conclusion: str = Field(..., description="Kesimpulan akhir dari perbandingan tersebut. JIKA di dalam konteks tidak ada 2 objek untuk dibandingan, kosongi blok comparison ini.")


class LegalReferenceItem(BaseModel):
    source_name: str = Field(..., description="Nama resmi undang-undang atau peraturan sumber hukum utama")
    article: str = Field(..., description="Nomor pasal atau ayat spesifik")
    excerpt: Optional[str] = Field(default=None, description="Cuplikan teks asli pasal yang dikutip langsung dari konteks")
    relevance: str = Field(..., description="Penjelasan singkat relevansi pasal terhadap skenario")


class MaterialResponse(BaseModel):
    summary: SummaryBlock = Field(..., description="Blok summary")
    clause_search: List[ClauseSearchItem] = Field(default_factory=list, description="Blok clause search")
    legal_qa: List[LegalQAItem] = Field(default_factory=list, description="Blok legal Q&A")
    risk_review: RiskReviewBlock = Field(..., description="Blok risk review")
    timeline_extraction: List[TimelineItem] = Field(default_factory=list, description="Blok timeline extraction. Jika di konteks tidak ada data waktu/durasi/tenggat, biarkan array ini kosong []")
    comparison: List[ComparisonItem] = Field(default_factory=list, description="Blok comparison. Jika di konteks tidak ada dua objek/pasal berbeda untuk dibandingan, biarkan array ini kosong []")
    referensi_uu: List[LegalReferenceItem] = Field(default_factory=list, description="Referensi UU otentik yang dirujuk dalam teks")

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