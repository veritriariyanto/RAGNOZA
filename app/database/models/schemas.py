from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
import uuid


# ─────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────

class HierarchyLevel(str, Enum):
    """Level hierarki dalam struktur undang-undang."""
    DOCUMENT = "document"   # Level 0 – Seluruh dokumen / judul UU
    BAB = "bab"             # Level 1 – BAB (e.g., BAB I KETENTUAN UMUM)
    PASAL = "pasal"         # Level 2 – Pasal (e.g., Pasal 1)
    AYAT = "ayat"           # Level 3 – Ayat/Paragraf (e.g., (1) ...)


class CleaningStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


# ─────────────────────────────────────────────
# CLEANING MODELS
# ─────────────────────────────────────────────

class PageContent(BaseModel):
    """Konten dari satu halaman PDF."""
    page_number: int
    raw_text: str
    cleaned_text: str = ""
    word_count: int = 0
    char_count: int = 0


# ─────────────────────────────────────────────
# PARSED STRUCTURE MODELS
# ─────────────────────────────────────────────

class BabEntry(BaseModel):
    """Satu entri BAB yang terdeteksi dalam dokumen UU."""
    number: str                         # "I", "II", "III", "1", "2"
    title: str = ""                     # "KETENTUAN UMUM"
    full_header: str                    # "BAB I\nKETENTUAN UMUM"
    char_start: int                     # posisi karakter dalam full_cleaned_text
    pasal_start: Optional[int] = None  # nomor Pasal pertama di BAB ini
    pasal_end: Optional[int] = None    # nomor Pasal terakhir di BAB ini
    pasal_count: int = 0               # jumlah Pasal dalam BAB ini


class PasalEntry(BaseModel):
    """Satu entri Pasal yang terdeteksi dalam dokumen UU."""
    number: str                         # "1", "2", "3A"
    full_header: str                    # "Pasal 1"
    char_start: int                     # posisi karakter dalam full_cleaned_text
    bab_number: Optional[str] = None   # BAB induk tempat Pasal ini berada
    ayat_count: int = 0                # jumlah ayat terdeteksi


class ParsedStructure(BaseModel):
    """Hasil pra-parsing struktur hierarki dokumen UU."""
    bab_list: List[BabEntry] = []
    pasal_list: List[PasalEntry] = []
    total_bab: int = 0
    total_pasal: int = 0
    total_ayat: int = 0


class CleaningResult(BaseModel):
    """Hasil dari proses cleaning satu dokumen."""
    document_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_filename: str
    total_pages: int
    cleaned_pages: List[PageContent] = []
    full_cleaned_text: str = ""
    metadata: dict = {}
    parsed_structure: ParsedStructure = Field(default_factory=ParsedStructure)
    status: CleaningStatus = CleaningStatus.SUCCESS
    issues: List[str] = []
    repair_stats: dict = Field(
        default_factory=lambda: {
            "hyphenation_fixes":     0,
            "spaced_char_fixes":     0,
            "ocr_noise_fixes":       0,
            "broken_sentence_fixes": 0,
            "total_fixes":           0,
            "was_repaired":          False,
        },
        description=(
            "Statistik text repair: jumlah perbaikan per kategori. "
            "was_repaired=True jika minimal satu perbaikan dilakukan."
        ),
    )

    @property
    def total_words(self) -> int:
        return sum(p.word_count for p in self.cleaned_pages)


# ─────────────────────────────────────────────
# CHUNKING MODELS
# ─────────────────────────────────────────────

class ChunkMetadata(BaseModel):
    """Metadata yang melekat pada setiap chunk."""
    document_id: str
    source_filename: str
    hierarchy_level: HierarchyLevel
    level_number: int  # 0, 1, 2, 3

    # Konteks hierarki
    document_title: Optional[str] = None
    bab_title: Optional[str] = None       # "BAB I KETENTUAN UMUM"
    bab_number: Optional[str] = None      # "I"
    pasal_title: Optional[str] = None     # "Pasal 1"
    pasal_number: Optional[int] = None    # 1
    ayat_number: Optional[int] = None     # 1

    # Posisi dalam dokumen
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    chunk_index: int = 0
    total_chunks: int = 0
    token_count: int = 0

    # Relasi hierarki (untuk navigasi)
    parent_chunk_id: Optional[str] = None
    child_chunk_ids: List[str] = []

    # Tipe chunk dalam parent-child pattern
    # True  = chunk ini adalah PARENT (konten agregat, dipakai sebagai konteks)
    # False = chunk ini adalah CHILD  (unit kecil, di-embed untuk vector search)
    is_parent: bool = False


class DocumentChunk(BaseModel):
    """Satu unit chunk dari dokumen UU."""
    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    metadata: ChunkMetadata
    embedding: Optional[List[float]] = None  # diisi saat indexing ke Qdrant

    @property
    def preview(self) -> str:
        return self.content[:150] + "..." if len(self.content) > 150 else self.content


class ChunkingResult(BaseModel):
    """Hasil proses hierarchical chunking satu dokumen."""
    document_id: str
    source_filename: str
    total_chunks: int = 0

    # Breakdown per level
    level_0_chunks: List[DocumentChunk] = []  # Document level
    level_1_chunks: List[DocumentChunk] = []  # BAB level
    level_2_chunks: List[DocumentChunk] = []  # Pasal level
    level_3_chunks: List[DocumentChunk] = []  # Ayat level

    metadata: dict = {}

    @property
    def all_chunks(self) -> List[DocumentChunk]:
        return (
            self.level_0_chunks
            + self.level_1_chunks
            + self.level_2_chunks
            + self.level_3_chunks
        )


# ─────────────────────────────────────────────
# API REQUEST/RESPONSE MODELS
# ─────────────────────────────────────────────

class ProcessingResponse(BaseModel):
    """Response standar untuk semua endpoint."""
    success: bool
    message: str
    document_id: Optional[str] = None
    data: Optional[dict] = None


class CleaningStats(BaseModel):
    total_pages: int
    total_words: int
    total_chars: int
    issues_found: int


class ChunkingStats(BaseModel):
    total_chunks: int
    level_0_count: int
    level_1_count: int
    level_2_count: int
    level_3_count: int
    avg_tokens_per_chunk: float