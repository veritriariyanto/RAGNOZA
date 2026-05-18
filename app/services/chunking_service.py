"""
app/services/chunking_service.py
=================================
Implementasi PARENT-CHILD CHUNKING untuk dokumen UU Indonesia.

Konsep:
┌─────────────────────────────────────────────────────────────┐
│  PARENT chunk: Konten PENUH satu unit hierarki (konteks)    │
│  CHILD chunk:  Unit KECIL yang di-embed & di-retrieve       │
│                                                             │
│  Document (L0) → parent semua BAB                           │
│      BAB (L1 parent) → konten penuh semua Pasal+Ayat        │
│          Pasal (L2 parent) → konten penuh semua Ayat        │
│              Ayat (L3 child) → unit retrieval kecil         │
│                                                             │
│  Pasal tanpa Ayat → Pasal menjadi child langsung            │
└─────────────────────────────────────────────────────────────┘

Alur RAG:
  1. Vector search → temukan CHILD chunk yang relevan
  2. Baca parent_chunk_id → fetch PARENT sebagai konteks penuh
  3. LLM menerima konteks lengkap, bukan hanya potongan kecil
"""

import uuid
from typing import Optional
import logging

logger = logging.getLogger(__name__)

from app.models.schemas import (
    ChunkingResult,
    DocumentChunk,
    ChunkMetadata,
    HierarchyLevel,
    CleaningResult,
)
from app.utils.uu_patterns import detect_structure_level
from app.utils.text_utils import count_tokens, normalize_whitespace
from app.config import settings


# ─────────────────────────────────────────────
# INTERNAL DATA CLASS
# ─────────────────────────────────────────────

class _HierarchyNode:
    """Node internal untuk membangun pohon hierarki sebelum di-chunk."""
    def __init__(self, level: str, title: str, number: str = ""):
        self.level = level
        self.title = title
        self.number = number
        self.lines: list[str] = []
        self.children: list["_HierarchyNode"] = []
        self.page_start: Optional[int] = None
        self.page_end: Optional[int] = None

    @property
    def content(self) -> str:
        return normalize_whitespace("\n".join(self.lines))


# ─────────────────────────────────────────────
# CHUNKING SERVICE
# ─────────────────────────────────────────────

class ChunkingService:
    """
    Parent-Child Chunking untuk dokumen UU Indonesia.

    - Parent chunks (L0-L2): Konten agregat penuh, dipakai sebagai konteks RAG
    - Child chunks (L3 Ayat, L2 Pasal tanpa Ayat): Unit kecil untuk vector search
    - Setiap child memiliki parent_chunk_id → fetch konteks saat retrieval
    """

    def __init__(self):
        self.max_tokens = {
            0: settings.chunk_level_1_max_tokens,  # Document
            1: settings.chunk_level_1_max_tokens,  # BAB parent
            2: settings.chunk_level_2_max_tokens,  # Pasal parent/child
            3: settings.chunk_level_3_max_tokens,  # Ayat child
        }
        self.overlap_tokens = settings.chunk_overlap_tokens
        self.min_tokens = settings.chunk_min_tokens

    # ──────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────

    async def chunk(self, cleaning_result: CleaningResult) -> ChunkingResult:
        """Entry point: terima CleaningResult, hasilkan ChunkingResult."""
        logger.info(f"[CHUNKING] Mulai parent-child chunking: {cleaning_result.source_filename}")

        result = ChunkingResult(
            document_id=cleaning_result.document_id,
            source_filename=cleaning_result.source_filename,
            metadata=cleaning_result.metadata,
        )

        full_text = cleaning_result.full_cleaned_text
        if not full_text.strip():
            logger.warning("[CHUNKING] Teks kosong, tidak ada chunk yang dibuat")
            return result

        doc_node = self._parse_to_hierarchy(full_text)
        doc_title = self._build_document_title(cleaning_result.metadata)
        doc_id = cleaning_result.document_id
        src = cleaning_result.source_filename

        # ── L0: Document parent ──────────────────────────────────
        doc_chunk = self._make_document_chunk(doc_node, doc_id, src, doc_title)
        result.level_0_chunks = [doc_chunk]

        level_1: list[DocumentChunk] = []
        level_2: list[DocumentChunk] = []
        level_3: list[DocumentChunk] = []

        for bab_node in doc_node.children:

            # ── L1: BAB parent (konten penuh: judul + semua Pasal + Ayat) ──
            bab_full = self._aggregate_node_text(bab_node, depth=2)
            bab_chunks = self._split_to_chunks(
                content=bab_full,
                document_id=doc_id,
                source_filename=src,
                hierarchy_level=HierarchyLevel.BAB,
                level_number=1,
                doc_title=doc_title,
                bab_title=bab_node.title,
                bab_number=bab_node.number,
                parent_id=doc_chunk.chunk_id,
                max_tokens=self.max_tokens[1],
                is_parent=True,  # BAB = parent
            )
            level_1.extend(bab_chunks)
            bab_parent_id = bab_chunks[0].chunk_id if bab_chunks else doc_chunk.chunk_id

            for pasal_node in bab_node.children:

                if pasal_node.children:
                    # ── L2: Pasal parent (konten penuh: judul + semua Ayat) ──
                    pasal_full = self._aggregate_node_text(pasal_node, depth=1)
                    pasal_chunks = self._split_to_chunks(
                        content=pasal_full,
                        document_id=doc_id,
                        source_filename=src,
                        hierarchy_level=HierarchyLevel.PASAL,
                        level_number=2,
                        doc_title=doc_title,
                        bab_title=bab_node.title,
                        bab_number=bab_node.number,
                        pasal_title=pasal_node.title,
                        pasal_number=self._to_int(pasal_node.number),
                        parent_id=bab_parent_id,
                        max_tokens=self.max_tokens[2],
                        is_parent=True,  # Pasal dengan Ayat = parent
                    )
                    level_2.extend(pasal_chunks)
                    pasal_parent_id = pasal_chunks[0].chunk_id if pasal_chunks else bab_parent_id

                    for ayat_node in pasal_node.children:
                        # ── L3: Ayat child (unit kecil untuk vector search) ──
                        ayat_content = ayat_node.content or ayat_node.title
                        ayat_chunks = self._split_to_chunks(
                            content=ayat_content,
                            document_id=doc_id,
                            source_filename=src,
                            hierarchy_level=HierarchyLevel.AYAT,
                            level_number=3,
                            doc_title=doc_title,
                            bab_title=bab_node.title,
                            bab_number=bab_node.number,
                            pasal_title=pasal_node.title,
                            pasal_number=self._to_int(pasal_node.number),
                            ayat_number=self._to_int(ayat_node.number),
                            parent_id=pasal_parent_id,
                            max_tokens=self.max_tokens[3],
                            is_parent=False,  # Ayat = child
                        )
                        level_3.extend(ayat_chunks)

                else:
                    # ── L2: Pasal child (leaf — tidak punya Ayat) ──
                    pasal_content = self._aggregate_node_text(pasal_node, depth=0)
                    pasal_chunks = self._split_to_chunks(
                        content=pasal_content,
                        document_id=doc_id,
                        source_filename=src,
                        hierarchy_level=HierarchyLevel.PASAL,
                        level_number=2,
                        doc_title=doc_title,
                        bab_title=bab_node.title,
                        bab_number=bab_node.number,
                        pasal_title=pasal_node.title,
                        pasal_number=self._to_int(pasal_node.number),
                        parent_id=bab_parent_id,
                        max_tokens=self.max_tokens[2],
                        is_parent=False,  # Pasal tanpa Ayat = leaf/child
                    )
                    level_2.extend(pasal_chunks)

        result.level_1_chunks = level_1
        result.level_2_chunks = level_2
        result.level_3_chunks = level_3
        result.total_chunks = len(result.all_chunks)

        all_tokens = [count_tokens(c.content) for c in result.all_chunks]
        avg_tokens = sum(all_tokens) / len(all_tokens) if all_tokens else 0

        logger.info(
            f"[CHUNKING] Selesai (parent-child): "
            f"L0={len(result.level_0_chunks)}, "
            f"L1={len(result.level_1_chunks)} BAB, "
            f"L2={len(result.level_2_chunks)} Pasal, "
            f"L3={len(result.level_3_chunks)} Ayat | "
            f"Total={result.total_chunks} | "
            f"Avg {avg_tokens:.0f} tokens/chunk"
        )
        return result

    # ──────────────────────────────────────────────────────────────
    # STEP 1: PARSE TEKS → POHON HIERARKI
    # ──────────────────────────────────────────────────────────────

    def _parse_to_hierarchy(self, text: str) -> _HierarchyNode:
        """
        Parse teks UU menjadi pohon hierarki:
        Document → BAB → Pasal → Ayat (single-pass scanning).
        """
        doc_node = _HierarchyNode(level="document", title="Document Root")
        current_bab: Optional[_HierarchyNode] = None
        current_pasal: Optional[_HierarchyNode] = None
        current_ayat: Optional[_HierarchyNode] = None

        lines = text.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            level_name, match = detect_structure_level(line)

            if level_name == "bab":
                bab_title = stripped
                # Cek apakah baris berikutnya adalah kelanjutan nama BAB
                if i + 1 < len(lines) and lines[i + 1].strip():
                    next_line = lines[i + 1].strip()
                    nxt_level, _ = detect_structure_level(next_line)
                    if nxt_level not in ("bab", "pasal", "ayat", "bagian"):
                        bab_title = f"{stripped} {next_line}"
                        i += 1

                current_bab = _HierarchyNode(
                    level="bab", title=bab_title, number=match.number
                )
                doc_node.children.append(current_bab)
                current_pasal = None
                current_ayat = None

            elif level_name == "pasal":
                current_pasal = _HierarchyNode(
                    level="pasal", title=stripped, number=match.number
                )
                if current_bab is not None:
                    current_bab.children.append(current_pasal)
                else:
                    if not doc_node.children:
                        dummy_bab = _HierarchyNode(level="bab", title="BAB UMUM", number="0")
                        doc_node.children.append(dummy_bab)
                    doc_node.children[-1].children.append(current_pasal)
                current_ayat = None

            elif level_name == "ayat":
                current_ayat = _HierarchyNode(
                    level="ayat", title=match.title, number=match.number
                )
                current_ayat.lines.append(stripped)
                if current_pasal is not None:
                    current_pasal.children.append(current_ayat)

            else:
                if stripped:
                    if current_ayat is not None:
                        current_ayat.lines.append(stripped)
                    elif current_pasal is not None:
                        current_pasal.lines.append(stripped)
                    elif current_bab is not None:
                        current_bab.lines.append(stripped)
                    else:
                        doc_node.lines.append(stripped)

            i += 1

        logger.debug(
            f"[CHUNKING] Parse selesai: "
            f"{len(doc_node.children)} BAB, "
            f"{sum(len(b.children) for b in doc_node.children)} Pasal"
        )
        return doc_node

    # ──────────────────────────────────────────────────────────────
    # STEP 2: AGGREGASI TEKS (untuk parent chunks)
    # ──────────────────────────────────────────────────────────────

    def _aggregate_node_text(self, node: _HierarchyNode, depth: int = 1) -> str:
        """
        Kumpulkan teks dari node secara rekursif sampai kedalaman `depth`.

        depth=0 → hanya judul + baris langsung node
        depth=1 → termasuk children langsung
        depth=2 → termasuk grandchildren (Ayat dalam BAB)
        """
        parts: list[str] = []
        if node.title:
            parts.append(node.title)
        parts.extend(node.lines)

        if depth > 0:
            for child in node.children:
                child_text = self._aggregate_node_text(child, depth - 1)
                if child_text:
                    parts.append(child_text)

        return normalize_whitespace("\n".join(p for p in parts if p))

    # ──────────────────────────────────────────────────────────────
    # STEP 3: GENERATE CHUNKS
    # ──────────────────────────────────────────────────────────────

    def _make_document_chunk(
        self,
        doc_node: _HierarchyNode,
        document_id: str,
        source_filename: str,
        doc_title: str,
    ) -> DocumentChunk:
        """Buat chunk Level 0: ringkasan/header dokumen (intro sebelum BAB I)."""
        intro_lines = doc_node.lines[:50]
        content = normalize_whitespace("\n".join(intro_lines)) or doc_title

        metadata = ChunkMetadata(
            document_id=document_id,
            source_filename=source_filename,
            hierarchy_level=HierarchyLevel.DOCUMENT,
            level_number=0,
            document_title=doc_title,
            chunk_index=0,
            total_chunks=1,
            token_count=count_tokens(content),
            is_parent=True,  # Document selalu parent
        )
        return DocumentChunk(
            chunk_id=str(uuid.uuid4()), content=content, metadata=metadata
        )

    def _split_to_chunks(
        self,
        content: str,
        document_id: str,
        source_filename: str,
        hierarchy_level: HierarchyLevel,
        level_number: int,
        doc_title: str,
        max_tokens: int,
        parent_id: Optional[str] = None,
        bab_title: Optional[str] = None,
        bab_number: Optional[str] = None,
        pasal_title: Optional[str] = None,
        pasal_number: Optional[int] = None,
        ayat_number: Optional[int] = None,
        is_parent: bool = False,
    ) -> list[DocumentChunk]:
        """
        Bagi konten menjadi chunks dengan batas token.
        Jika konten < min_tokens → buang.
        Jika konten ≤ max_tokens → satu chunk.
        Jika konten > max_tokens → split dengan overlap.
        """
        content = content.strip()
        if not content or count_tokens(content) < self.min_tokens:
            return []

        context_prefix = self._build_context_prefix(
            doc_title, bab_title, pasal_title, ayat_number
        )
        sub_contents = self._token_split_with_overlap(content, max_tokens)
        chunks: list[DocumentChunk] = []

        for idx, sub_content in enumerate(sub_contents):
            full_content = (
                f"{context_prefix}\n\n{sub_content}".strip()
                if context_prefix
                else sub_content
            )
            metadata = ChunkMetadata(
                document_id=document_id,
                source_filename=source_filename,
                hierarchy_level=hierarchy_level,
                level_number=level_number,
                document_title=doc_title,
                bab_title=bab_title,
                bab_number=bab_number,
                pasal_title=pasal_title,
                pasal_number=pasal_number,
                ayat_number=ayat_number,
                chunk_index=idx,
                total_chunks=len(sub_contents),
                token_count=count_tokens(full_content),
                parent_chunk_id=parent_id,
                is_parent=is_parent,
            )
            chunks.append(
                DocumentChunk(
                    chunk_id=str(uuid.uuid4()),
                    content=full_content,
                    metadata=metadata,
                )
            )
        return chunks

    # ──────────────────────────────────────────────────────────────
    # TOKEN SPLIT + OVERLAP
    # ──────────────────────────────────────────────────────────────

    def _token_split_with_overlap(self, text: str, max_tokens: int) -> list[str]:
        """Split teks berdasarkan batas token dengan overlap per baris."""
        if count_tokens(text) <= max_tokens:
            return [text]

        lines = [l for l in text.split("\n") if l.strip()]
        chunks: list[str] = []
        current_lines: list[str] = []
        current_tokens = 0

        for line in lines:
            line_tokens = count_tokens(line)
            if current_tokens + line_tokens > max_tokens and current_lines:
                chunks.append("\n".join(current_lines))
                overlap_lines = self._get_overlap_lines(current_lines)
                current_lines = overlap_lines + [line]
                current_tokens = sum(count_tokens(l) for l in current_lines)
            else:
                current_lines.append(line)
                current_tokens += line_tokens

        if current_lines:
            chunks.append("\n".join(current_lines))

        return chunks if chunks else [text]

    def _get_overlap_lines(self, lines: list[str]) -> list[str]:
        """Ambil baris-baris terakhir sebagai overlap untuk chunk berikutnya."""
        overlap_lines: list[str] = []
        token_count = 0
        for line in reversed(lines):
            t = count_tokens(line)
            if token_count + t > self.overlap_tokens:
                break
            overlap_lines.insert(0, line)
            token_count += t
        return overlap_lines

    # ──────────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────────

    def _build_context_prefix(
        self,
        doc_title: Optional[str],
        bab_title: Optional[str],
        pasal_title: Optional[str],
        ayat_number: Optional[int],
    ) -> str:
        """
        Bangun context prefix untuk setiap chunk agar LLM/RAG memahami
        posisi chunk dalam hierarki dokumen.

        Contoh output:
        [Dokumen: UU No. 11 Tahun 2008 tentang ITE]
        [BAB: BAB I KETENTUAN UMUM]
        [Pasal: Pasal 1]
        [Ayat: (1)]
        """
        parts: list[str] = []
        if doc_title:
            parts.append(f"[Dokumen: {doc_title}]")
        if bab_title:
            parts.append(f"[BAB: {bab_title}]")
        if pasal_title:
            parts.append(f"[Pasal: {pasal_title}]")
        if ayat_number is not None:
            parts.append(f"[Ayat: ({ayat_number})]")
        return "\n".join(parts)

    def _build_document_title(self, metadata: dict) -> str:
        """Bangun judul dokumen dari metadata."""
        if not metadata:
            return "Dokumen Hukum"
        parts: list[str] = []
        if metadata.get("jenis"):
            parts.append(metadata["jenis"])
        if metadata.get("nomor") and metadata.get("tahun"):
            parts.append(f"No. {metadata['nomor']} Tahun {metadata['tahun']}")
        if metadata.get("tentang"):
            parts.append(f"tentang {metadata['tentang']}")
        return " ".join(parts) if parts else "Dokumen Hukum"

    @staticmethod
    def _to_int(value: str) -> Optional[int]:
        """Convert string ke int, return None jika gagal."""
        try:
            return int(value)
        except (ValueError, TypeError):
            return None