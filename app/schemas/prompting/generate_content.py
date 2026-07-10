# app/schemas/prompting/generate_content.py

# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field
from typing import Optional


class MaterialRequest(BaseModel):
    context_text: str = Field(
        ..., description="Dokumen UU atau aturan hukum terkait (dari hasil retrieval RAG)")
    user_scenario: str = Field(
        ..., description="Kasus nyata atau rencana tindakan yang ingin di-evaluasi oleh pengguna")
    raw_transcribe: Optional[str] = Field(
        default="", description="Teks transkripsi mentah sebelum repair")


class DasarHukum(BaseModel):
    nama_peraturan: str = Field(description="Nama UU/Peraturan, mis. 'UU No. 2 Tahun 2002'")
    pasal: str = Field(description="Nomor pasal, mis. 'Pasal 20'")
    ayat: Optional[str] = Field(default="-", description="Ayat/huruf spesifik jika ada, mis. 'ayat (1) huruf b'")
    catatan_validasi: Optional[str] = Field(
        default="-",
        description="Isi HANYA jika user menyebut pasal yang salah/tidak ada di context — "
                     "jelaskan koreksinya di sini. Jika user tidak sebut pasal atau sebut pasal "
                     "yang benar, isi '-'."
    )


class RingkasanPoint(BaseModel):
    poin: str = Field(description="Satu poin ringkasan, bahasa mudah namun kata kunci hukum asli dipertahankan")


class ContohPelanggaran(BaseModel):
    skenario: str = Field(description="Contoh naratif singkat tindakan yang melanggar pasal ini")
    penjelasan: str = Field(description="Kenapa skenario itu melanggar, dikaitkan ke ayat/huruf spesifik")


class QAPair(BaseModel):
    pertanyaan: str
    jawaban: str


class MaterialResponse(BaseModel):
    dasar_hukum: list[DasarHukum] = Field(default_factory=list)
    ringkasan: list[RingkasanPoint] = Field(default_factory=list)
    konteks_tambahan: str = Field(default="-")
    analisa_risiko: list[ContohPelanggaran] = Field(default_factory=list)
    qa: list[QAPair] = Field(default_factory=list)

    @property
    def decision_status(self) -> str:
        # Fallback untuk kompatibilitas riwayat database
        return "-"

    @property
    def compliance_score(self) -> int:
        # Fallback untuk kompatibilitas riwayat database
        return 0

    @property
    def recommendation(self) -> str:
        # Fallback untuk kompatibilitas riwayat database
        return "-"

    @property
    def risk_analysis(self) -> list[str]:
        return [item.penjelasan for item in self.analisa_risiko]

    @property
    def legal_basis(self) -> list[str]:
        return [f"{item.nama_peraturan} {item.pasal} {item.ayat or ''}".strip() for item in self.dasar_hukum]
