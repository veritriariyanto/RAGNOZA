"""
app/services/chunking_service.py
=================================
Implementasi PARENT-CHILD CHUNKING untuk dokumen UU Indonesia.

Memanfaatkan parsed_structure dari CleaningResult untuk membelah teks
secara presisi berdasarkan batas BAB, Pasal, dan Ayat.

Hierarki Chunks:
- Level 0: Document (is_parent=True) -> header/intro sebelum BAB I
- Level 1: BAB (is_parent=True)      -> isi lengkap BAB (judul + pasal + ayat)
- Level 2: Pasal (is_parent=True jika ada ayat, is_parent=False jika tanpa ayat)
- Level 3: Ayat (is_parent=False)     -> unit terkecil untuk embedding & retrieval
"""

import uuid
import logging
import re
from typing import Optional, List, Tuple

# pyrefly: ignore [missing-import]
from app.database.models.schemas import (
    ChunkingResult,
    DocumentChunk,
    ChunkMetadata,
    HierarchyLevel,
    CleaningResult,
    BabEntry,
    PasalEntry,
)
from app.utils.text_utils import count_tokens, normalize_whitespace  # pyrefly: ignore [missing-import]
from app.config import settings  # pyrefly: ignore [missing-import]

logger = logging.getLogger(__name__)


class ChunkingService:
    """
    Parent-Child Chunking Service menggunakan parsed_structure hasil cleaning.
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

    async def chunk(self, cleaning_result: CleaningResult) -> ChunkingResult:
        """
        Membagi dokumen UU menjadi parent-child chunks memanfaatkan parsed_structure.
        """
        logger.info(f"[CHUNKING] Memulai parent-child chunking: {cleaning_result.source_filename}")

        result = ChunkingResult(
            document_id=cleaning_result.document_id,
            source_filename=cleaning_result.source_filename,
            metadata=cleaning_result.metadata,
        )

        full_text = cleaning_result.full_cleaned_text
        if not full_text.strip():
            logger.warning("[CHUNKING] Teks kosong, tidak ada chunk yang dibuat")
            return result

        doc_title = self._build_document_title(cleaning_result.metadata)
        doc_id = cleaning_result.document_id
        src = cleaning_result.source_filename

        # Sediakan list BAB dari parsed_structure
        bab_list = list(cleaning_result.parsed_structure.bab_list)
        pasal_list = list(cleaning_result.parsed_structure.pasal_list)

        # Jika bab_list kosong tetapi ada pasal, buat dummy BAB
        if not bab_list and pasal_list:
            dummy_bab = BabEntry(
                number="UMUM",
                title="KETENTUAN UMUM / TANPA BAB",
                full_header="BAB UMUM",
                char_start=pasal_list[0].char_start,
                pasal_count=len(pasal_list)
            )
            bab_list = [dummy_bab]

        # ── Level 0: Document Intro (Sebelum BAB I) ──────────────────
        first_bab_start = bab_list[0].char_start if bab_list else len(full_text)
        doc_intro = full_text[0:first_bab_start].strip()
        doc_content = doc_intro if doc_intro else doc_title

        doc_chunks = self._split_to_chunks(
            content=doc_content,
            document_id=doc_id,
            source_filename=src,
            hierarchy_level=HierarchyLevel.DOCUMENT,
            level_number=0,
            doc_title=doc_title,
            max_tokens=self.max_tokens[0],
            is_parent=True,
        )
        result.level_0_chunks = doc_chunks
        
        # Simpan chunk_id utama dokumen untuk parent references
        doc_parent_id = doc_chunks[0].chunk_id if doc_chunks else doc_id

        # ── Level 1, 2, dan 3: BAB, Pasal, & Ayat ────────────────────
        level_1_bab_chunks: List[DocumentChunk] = []
        level_2_pasal_chunks: List[DocumentChunk] = []
        level_3_ayat_chunks: List[DocumentChunk] = []

        for i, bab in enumerate(bab_list):
            bab_start = bab.char_start
            bab_end = bab_list[i + 1].char_start if i + 1 < len(bab_list) else len(full_text)
            bab_content = full_text[bab_start:bab_end].strip()

            # ── L1: BAB Parent Chunk ──
            bab_chunks = self._split_to_chunks(
                content=bab_content,
                document_id=doc_id,
                source_filename=src,
                hierarchy_level=HierarchyLevel.BAB,
                level_number=1,
                doc_title=doc_title,
                bab_title=bab.full_header.replace("\n", " "),
                bab_number=bab.number,
                parent_id=doc_parent_id,
                max_tokens=self.max_tokens[1],
                is_parent=True,
            )
            level_1_bab_chunks.extend(bab_chunks)
            bab_parent_id = bab_chunks[0].chunk_id if bab_chunks else doc_parent_id

            # Filter Pasal yang berada di dalam BAB ini
            bab_pasals = [p for p in pasal_list if bab_start <= p.char_start < bab_end]

            for pasal in bab_pasals:
                global_idx = pasal_list.index(pasal)
                
                # Batas akhir Pasal
                if global_idx + 1 < len(pasal_list):
                    pasal_end = min(pasal_list[global_idx + 1].char_start, bab_end)
                else:
                    pasal_end = bab_end

                pasal_content = full_text[pasal.char_start:pasal_end].strip()
                ayats = self._extract_ayats_from_pasal(pasal_content)

                if ayats:
                    # ── L2: Pasal Parent Chunk (is_parent=True) ──
                    pasal_chunks = self._split_to_chunks(
                        content=pasal_content,
                        document_id=doc_id,
                        source_filename=src,
                        hierarchy_level=HierarchyLevel.PASAL,
                        level_number=2,
                        doc_title=doc_title,
                        bab_title=bab.full_header.replace("\n", " "),
                        bab_number=bab.number,
                        pasal_title=pasal.full_header,
                        pasal_number=self._to_int(pasal.number),
                        parent_id=bab_parent_id,
                        max_tokens=self.max_tokens[2],
                        is_parent=True,
                    )
                    level_2_pasal_chunks.extend(pasal_chunks)
                    pasal_parent_id = pasal_chunks[0].chunk_id if pasal_chunks else bab_parent_id

                    # ── L3: Ayat Child Chunks (is_parent=False) ──
                    for ayat in ayats:
                        ayat_chunks = self._split_to_chunks(
                            content=ayat["content"],
                            document_id=doc_id,
                            source_filename=src,
                            hierarchy_level=HierarchyLevel.AYAT,
                            level_number=3,
                            doc_title=doc_title,
                            bab_title=bab.full_header.replace("\n", " "),
                            bab_number=bab.number,
                            pasal_title=pasal.full_header,
                            pasal_number=self._to_int(pasal.number),
                            ayat_number=ayat["ayat_number"],
                            parent_id=pasal_parent_id,
                            max_tokens=self.max_tokens[3],
                            is_parent=False,
                        )
                        level_3_ayat_chunks.extend(ayat_chunks)
                else:
                    # ── L2: Pasal Child Chunk (Leaf/Tanpa Ayat, is_parent=False) ──
                    pasal_chunks = self._split_to_chunks(
                        content=pasal_content,
                        document_id=doc_id,
                        source_filename=src,
                        hierarchy_level=HierarchyLevel.PASAL,
                        level_number=2,
                        doc_title=doc_title,
                        bab_title=bab.full_header.replace("\n", " "),
                        bab_number=bab.number,
                        pasal_title=pasal.full_header,
                        pasal_number=self._to_int(pasal.number),
                        parent_id=bab_parent_id,
                        max_tokens=self.max_tokens[2],
                        is_parent=False,
                    )
                    level_2_pasal_chunks.extend(pasal_chunks)

        result.level_1_chunks = level_1_bab_chunks
        result.level_2_chunks = level_2_pasal_chunks
        result.level_3_chunks = level_3_ayat_chunks
        result.total_chunks = len(result.all_chunks)

        all_tokens = [count_tokens(c.content) for c in result.all_chunks]
        avg_tokens = sum(all_tokens) / len(all_tokens) if all_tokens else 0

        logger.info(
            f"[CHUNKING] Selesai: L0={len(result.level_0_chunks)} Doc, "
            f"L1={len(result.level_1_chunks)} BAB, "
            f"L2={len(result.level_2_chunks)} Pasal, "
            f"L3={len(result.level_3_chunks)} Ayat | "
            f"Total={result.total_chunks} chunks | Rata-rata {avg_tokens:.1f} tokens/chunk"
        )
        return result

    # ── Helpers ──────────────────────────────────────────────────

    def _extract_ayats_from_pasal(self, pasal_content: str) -> List[dict]:
        """
        Mengekstrak ayat-ayat dari teks Pasal secara presisi menggunakan regex.
        """
        matches = list(re.finditer(r"(?:^|\n)\s*\((\d+)\)\s+", pasal_content))
        if not matches:
            return []

        ayats = []
        for idx, match in enumerate(matches):
            ayat_num = int(match.group(1))
            start_idx = match.start()
            end_idx = matches[idx + 1].start() if idx + 1 < len(matches) else len(pasal_content)
            ayat_text = pasal_content[start_idx:end_idx].strip()
            ayats.append({
                "ayat_number": ayat_num,
                "content": ayat_text
            })
        return ayats

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
    ) -> List[DocumentChunk]:
        """
        Membagi konten teks berdasarkan batas maksimum token dengan overlap.
        Menambahkan context prefix untuk meningkatkan retrieval accuracy pada child chunks.
        """
        content = content.strip()
        if not content or count_tokens(content) < self.min_tokens:
            return []

        context_prefix = self._build_context_prefix(
            doc_title, bab_title, pasal_title, ayat_number
        )
        
        # Bagi isi teks jika melebihi batas token maksimum
        sub_contents = self._token_split_with_overlap(content, max_tokens)
        chunks: List[DocumentChunk] = []

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

    def _token_split_with_overlap(self, text: str, max_tokens: int) -> List[str]:
        """
        Membelah teks berdasarkan token limit secara aman per baris dengan overlap.
        """
        if count_tokens(text) <= max_tokens:
            return [text]

        lines = [l for l in text.split("\n") if l.strip()]
        chunks: List[str] = []
        current_lines: List[str] = []
        current_tokens = 0

        for line in lines:
            line_tokens = count_tokens(line)
            if current_tokens + line_tokens > max_tokens and current_lines:
                chunks.append("\n".join(current_lines))
                # Ambil sisa baris untuk overlap
                overlap_lines = self._get_overlap_lines(current_lines)
                current_lines = overlap_lines + [line]
                current_tokens = sum(count_tokens(l) for l in current_lines)
            else:
                current_lines.append(line)
                current_tokens += line_tokens

        if current_lines:
            chunks.append("\n".join(current_lines))

        return chunks if chunks else [text]

    def _get_overlap_lines(self, lines: List[str]) -> List[str]:
        """
        Mengambil beberapa baris terakhir dari list baris untuk dijadikan overlap.
        """
        overlap_lines: List[str] = []
        token_count = 0
        for line in reversed(lines):
            t = count_tokens(line)
            if token_count + t > self.overlap_tokens:
                break
            overlap_lines.insert(0, line)
            token_count += t
        return overlap_lines

    def _build_context_prefix(
        self,
        doc_title: Optional[str],
        bab_title: Optional[str],
        pasal_title: Optional[str],
        ayat_number: Optional[int],
    ) -> str:
        """
        Membangun header penunjuk konteks (context prefix) untuk setiap chunk.
        """
        parts: List[str] = []
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
        """
        Membangun judul lengkap dokumen hukum dari metadata yang diekstrak.
        """
        if not metadata:
            return "Dokumen Hukum"
        parts: List[str] = []
        if metadata.get("jenis"):
            parts.append(metadata["jenis"])
        if metadata.get("nomor") and metadata.get("tahun"):
            parts.append(f"No. {metadata['nomor']} Tahun {metadata['tahun']}")
        if metadata.get("tentang"):
            parts.append(f"tentang {metadata['tentang']}")
        return " ".join(parts) if parts else "Dokumen Hukum"

    @staticmethod
    def _to_int(value: str) -> Optional[int]:
        """Convert string ke integer dengan aman."""
        try:
            # Ambil digit numerik pertama jika format nomor pasal berhuruf (misal '3A' -> 3)
            match = re.search(r"\d+", str(value))
            return int(match.group(0)) if match else None
        except (ValueError, TypeError):
            return None