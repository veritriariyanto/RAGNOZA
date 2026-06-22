"""
app/services/knowledgebase/chunking_service.py
=============================================
Parent-Child Chunking Service untuk dokumen hukum Indonesia.

Format output chunk sesuai contoh di app/document/:
  Parent:
    {
      "chunk_id":  "parent_konsiderans" | "parent_pasal_1" | "parent_penjelasan_pasal_1",
      "type":      "parent",
      "section":   "Konsiderans" | "Batang Tubuh" | "Penjelasan",
      "title":     str,
      "text":      str  ← teks lengkap/agregat pasal
      "metadata":  { "source": str, "bagian"/"pasal"/"pasal_rujukan": ... }
    }

  Child:
    {
      "chunk_id":  "child_konsiderans_menimbang_a" | "child_pasal_1_ayat_1" | ...,
      "type":      "child",
      "parent_id": str,
      "text":      str  ← unit kecil siap di-embed
      "metadata":  { "source": str, ... }
    }
"""

from __future__ import annotations

import re
import logging
from typing import List, Optional, Dict, Any

from app.database.models.schemas import (
    ChunkingResult,
    DocumentChunk,
    ChunkMetadata,
    HierarchyLevel,
    CleaningResult,
    BabEntry,
    PasalEntry,
)
from app.utils.text_utils import count_tokens, normalize_whitespace
from app.core.config import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# SERVICE
# ─────────────────────────────────────────────────────────

class ChunkingService:
    """
    Menghasilkan parent-child chunks dari CleaningResult.

    Setiap chunk direpresentasikan sebagai dict (sesuai format JSON contoh)
    dan juga dikemas dalam DocumentChunk (untuk pipeline Qdrant).
    """

    def __init__(self):
        self.max_tokens = {
            0: settings.chunk_level_1_max_tokens,
            1: settings.chunk_level_1_max_tokens,
            2: settings.chunk_level_2_max_tokens,
            3: settings.chunk_level_3_max_tokens,
        }
        self.overlap_tokens = settings.chunk_overlap_tokens
        self.min_tokens = settings.chunk_min_tokens

    async def chunk(self, cleaning_result: CleaningResult) -> ChunkingResult:
        """Entry point utama. Kembalikan ChunkingResult berisi semua chunk."""
        logger.info(
            f"[CHUNKING] Memulai parent-child chunking: {cleaning_result.source_filename}"
        )

        result = ChunkingResult(
            document_id=cleaning_result.document_id,
            source_filename=cleaning_result.source_filename,
            metadata=cleaning_result.metadata,
        )

        source_label = cleaning_result.metadata.get(
            "source_label",
            cleaning_result.source_filename.replace(".pdf", ""),
        )

        # --- Konsiderans chunks ---
        konsiderans = cleaning_result.__dict__.get("konsiderans", {})
        konsiderans_chunks = self._build_konsiderans_chunks(konsiderans, source_label)

        # --- Batang Tubuh chunks (per-pasal) ---
        pasal_data: List[dict] = cleaning_result.__dict__.get("pasal_data", [])
        if not pasal_data:
            pasal_data = self._fallback_pasal_data(cleaning_result)

        batang_chunks = self._build_batang_tubuh_chunks(pasal_data, source_label)

        # --- Penjelasan chunks ---
        penjelasan_text: str = cleaning_result.__dict__.get("penjelasan_text", "")
        penjelasan_chunks = self._build_penjelasan_chunks(penjelasan_text, source_label)

        # Gabungkan semua chunk dict ke result
        all_raw: List[dict] = konsiderans_chunks + batang_chunks + penjelasan_chunks

        # Simpan raw JSON-serializable chunks agar mudah diakses route
        result.__dict__["raw_chunks"] = all_raw

        # Konversi ke DocumentChunk untuk level breakdown (backward compat)
        doc_chunks = self._to_document_chunks(all_raw, cleaning_result.document_id, cleaning_result.source_filename)
        result.level_0_chunks = [c for c in doc_chunks if c.metadata.level_number == 0]
        result.level_1_chunks = [c for c in doc_chunks if c.metadata.level_number == 1]
        result.level_2_chunks = [c for c in doc_chunks if c.metadata.level_number == 2]
        result.level_3_chunks = [c for c in doc_chunks if c.metadata.level_number == 3]
        result.total_chunks = len(doc_chunks)

        logger.info(
            f"[CHUNKING] Selesai: {len(konsiderans_chunks)} Konsiderans, "
            f"{len(batang_chunks)} Batang Tubuh, "
            f"{len(penjelasan_chunks)} Penjelasan | "
            f"Total={result.total_chunks} chunks"
        )
        return result

    # ─────────────────────────────────────────────────────
    # KONSIDERANS
    # ─────────────────────────────────────────────────────

    def _build_konsiderans_chunks(
        self, konsiderans: dict, source_label: str
    ) -> List[dict]:
        """
        Bangun parent + child chunks untuk bagian Konsiderans.

        Parent: teks gabungan Menimbang + Mengingat
        Child per poin Menimbang (a, b, c, …)
        """
        chunks: List[dict] = []
        if not konsiderans:
            return chunks

        menimbang: List[dict] = konsiderans.get("menimbang", [])
        mengingat: str = konsiderans.get("mengingat", "")
        full_text: str = konsiderans.get("full_text", "")

        if not menimbang and not mengingat:
            return chunks

        parent_id = "parent_konsiderans"

        # Susun teks parent dari poin menimbang + mengingat
        parent_lines = []
        if menimbang:
            parent_lines.append("Menimbang:")
            for item in menimbang:
                parent_lines.append(f"{item['huruf']}. {item['text']}")
        if mengingat:
            parent_lines.append(f"Mengingat: {mengingat}")

        parent_text = full_text if full_text else "\n".join(parent_lines)

        chunks.append({
            "chunk_id": parent_id,
            "type": "parent",
            "section": "Konsiderans",
            "title": "Menimbang dan Mengingat",
            "text": parent_text,
            "metadata": {
                "source": source_label,
                "bagian": "Konsiderans",
            },
        })

        # Child per poin Menimbang
        for item in menimbang:
            huruf = item["huruf"]
            chunks.append({
                "chunk_id": f"child_konsiderans_menimbang_{huruf}",
                "type": "child",
                "section": "Konsiderans",
                "parent_id": parent_id,
                "text": f"Menimbang huruf {huruf}: {item['text']}",
                "metadata": {
                    "source": source_label,
                    "bagian": "Konsiderans",
                    "poin": huruf,
                },
            })

        # Child Mengingat (satu unit)
        if mengingat:
            chunks.append({
                "chunk_id": "child_konsiderans_mengingat",
                "type": "child",
                "section": "Konsiderans",
                "parent_id": parent_id,
                "text": f"Mengingat: {mengingat}",
                "metadata": {
                    "source": source_label,
                    "bagian": "Konsiderans",
                    "poin": "mengingat",
                },
            })

        return chunks

    # ─────────────────────────────────────────────────────
    # BATANG TUBUH
    # ─────────────────────────────────────────────────────

    def _build_batang_tubuh_chunks(
        self, pasal_data: List[dict], source_label: str
    ) -> List[dict]:
        """
        Bangun parent + child chunks untuk setiap pasal di Batang Tubuh.

        Parent: teks lengkap pasal (semua ayat)
        Child:
          - Jika pasal memiliki ayat bernomor → satu child per ayat
          - Jika pasal tunggal (tidak ada ayat) → satu child dengan teks pasal
          - Jika pasal Ketentuan Umum (Pasal 1 dengan poin angka) → satu child per poin
        """
        chunks: List[dict] = []

        for pasal in pasal_data:
            pasal_number = pasal.get("pasal_number", "")
            pasal_title = pasal.get("title", f"Pasal {pasal_number}")
            full_text = pasal.get("full_text", "")
            ayat_list: List[dict] = pasal.get("ayat_list", [])
            section = pasal.get("section", "Batang Tubuh")

            if not full_text.strip():
                continue

            parent_id = f"parent_pasal_{pasal_number}"

            # Pastikan pasal_number bisa jadi int
            pasal_num_int = _to_int(pasal_number)

            chunks.append({
                "chunk_id": parent_id,
                "type": "parent",
                "section": section,
                "title": pasal_title,
                "text": full_text,
                "metadata": {
                    "source": source_label,
                    "pasal": pasal_num_int if pasal_num_int is not None else pasal_number,
                },
            })

            # ── Buat child chunks ─────────────────────────
            for ayat in ayat_list:
                ayat_number = ayat.get("ayat_number")
                ayat_text = ayat.get("text", "").strip()
                poin_list: List[dict] = ayat.get("poin_list", [])

                if not ayat_text:
                    continue

                if ayat_number == "tunggal":
                    # Pasal tanpa ayat bernomor
                    if poin_list:
                        # Ada poin huruf atau angka → satu child per poin
                        for poin in poin_list:
                            huruf = poin.get("huruf", "")
                            poin_text = poin.get("text", "")
                            chunks.append({
                                "chunk_id": f"child_pasal_{pasal_number}_poin_{huruf}",
                                "type": "child",
                                "section": section,
                                "parent_id": parent_id,
                                "text": f"Pasal {pasal_number} Poin {huruf}: {poin_text}",
                                "metadata": {
                                    "source": source_label,
                                    "pasal": pasal_num_int if pasal_num_int is not None else pasal_number,
                                    "poin": huruf,
                                },
                            })
                    else:
                        # Pasal tunggal tanpa poin
                        # Hapus prefix "Pasal N" yang sudah ada di ayat_text agar tidak duplikat
                        clean_ayat = re.sub(
                            rf"^\s*Pasal\s+{re.escape(str(pasal_number))}\s*\n?",
                            "", ayat_text, flags=re.IGNORECASE
                        ).strip()
                        chunks.append({
                            "chunk_id": f"child_pasal_{pasal_number}_tunggal",
                            "type": "child",
                            "section": section,
                            "parent_id": parent_id,
                            "text": f"Pasal {pasal_number}: {clean_ayat}",
                            "metadata": {
                                "source": source_label,
                                "pasal": pasal_num_int if pasal_num_int is not None else pasal_number,
                            },
                        })
                else:
                    # Pasal dengan ayat bernomor
                    ayat_int = int(ayat_number) if str(ayat_number).isdigit() else ayat_number
                    ayat_label = _get_pasal_title_without_prefix(pasal_title, pasal_number)

                    child_text = f"Pasal {pasal_number} Ayat ({ayat_int}) mengenai {ayat_label}"

                    chunks.append({
                        "chunk_id": f"child_pasal_{pasal_number}_ayat_{ayat_int}",
                        "type": "child",
                        "section": section,
                        "parent_id": parent_id,
                        "text": child_text,
                        "metadata": {
                            "source": source_label,
                            "pasal": pasal_num_int if pasal_num_int is not None else pasal_number,
                            "ayat": ayat_int,
                        },
                    })

                    # Child poin dalam ayat (opsional, jika ada)
                    if poin_list:
                        for poin in poin_list:
                            huruf = poin.get("huruf", "")
                            poin_text = poin.get("text", "")
                            chunks.append({
                                "chunk_id": f"child_pasal_{pasal_number}_ayat_{ayat_int}_huruf_{huruf}",
                                "type": "child",
                                "section": section,
                                "parent_id": parent_id,
                                "text": f"Pasal {pasal_number} Ayat ({ayat_int}) huruf {huruf}: {poin_text}",
                                "metadata": {
                                    "source": source_label,
                                    "pasal": pasal_num_int if pasal_num_int is not None else pasal_number,
                                    "ayat": ayat_int,
                                    "huruf": huruf,
                                },
                            })

        return chunks

    # ─────────────────────────────────────────────────────
    # PENJELASAN
    # ─────────────────────────────────────────────────────

    def _build_penjelasan_chunks(
        self, penjelasan_text: str, source_label: str
    ) -> List[dict]:
        """
        Bangun parent + child chunks untuk bagian Penjelasan.

        Penjelasan diparse per-pasal yang disebut (Pasal X).
        """
        chunks: List[dict] = []
        if not penjelasan_text.strip():
            return chunks

        pasal_sections = _split_penjelasan_by_pasal(penjelasan_text)

        if not pasal_sections:
            # Tidak ada referensi pasal spesifik → satu parent tunggal
            parent_id = "parent_penjelasan_umum"
            chunks.append({
                "chunk_id": parent_id,
                "type": "parent",
                "section": "Penjelasan",
                "title": "Penjelasan Umum",
                "text": penjelasan_text.strip(),
                "metadata": {
                    "source": source_label,
                    "bagian": "Penjelasan",
                },
            })
            chunks.append({
                "chunk_id": "child_penjelasan_umum_isi",
                "type": "child",
                "section": "Penjelasan",
                "parent_id": parent_id,
                "text": penjelasan_text.strip(),
                "metadata": {
                    "source": source_label,
                    "bagian": "Penjelasan",
                },
            })
            return chunks

        for pasal_number, section_text in pasal_sections:
            pasal_num_int = _to_int(str(pasal_number))
            parent_id = f"parent_penjelasan_pasal_{pasal_number}"

            parent_text = f"II. PASAL DEMI PASAL\nPasal {pasal_number}\n{section_text.strip()}"

            chunks.append({
                "chunk_id": parent_id,
                "type": "parent",
                "section": "Penjelasan",
                "title": f"Penjelasan Pasal {pasal_number}",
                "text": parent_text,
                "metadata": {
                    "source": source_label,
                    "pasal_rujukan": pasal_num_int if pasal_num_int is not None else pasal_number,
                },
            })
            chunks.append({
                "chunk_id": f"child_penjelasan_pasal_{pasal_number}_isi",
                "type": "child",
                "section": "Penjelasan",
                "parent_id": parent_id,
                "text": f"Tafsir Resmi Pasal {pasal_number}: {section_text.strip()}",
                "metadata": {
                    "source": source_label,
                    "pasal_rujukan": pasal_num_int if pasal_num_int is not None else pasal_number,
                },
            })

        return chunks

    # ─────────────────────────────────────────────────────
    # FALLBACK (jika pasal_data kosong)
    # ─────────────────────────────────────────────────────

    def _fallback_pasal_data(self, cleaning_result: CleaningResult) -> List[dict]:
        """
        Jika CleaningService tidak menghasilkan pasal_data (dokumen sederhana),
        coba parse langsung dari full_cleaned_text menggunakan parsed_structure.
        """
        pasal_data = []
        full_text = cleaning_result.full_cleaned_text
        pasal_list = list(cleaning_result.parsed_structure.pasal_list)

        for i, pasal in enumerate(pasal_list):
            start = pasal.char_start
            end = pasal_list[i + 1].char_start if i + 1 < len(pasal_list) else len(full_text)
            pasal_text = full_text[start:end].strip()

            from app.services.knowlagebase.cleaning_service import (
                _extract_ayats, _build_pasal_title
            )
            ayat_list = _extract_ayats(pasal_text, pasal.number)
            title = _build_pasal_title(pasal.number, pasal_text)

            pasal_data.append({
                "pasal_number": pasal.number,
                "section": "Batang Tubuh",
                "bab_number": pasal.bab_number or "",
                "bab_title": "",
                "full_text": pasal_text,
                "ayat_list": ayat_list,
                "title": title,
                "char_start": start,
            })

        return pasal_data

    # ─────────────────────────────────────────────────────
    # CONVERT TO DOCUMENT CHUNKS (Qdrant pipeline compat)
    # ─────────────────────────────────────────────────────

    def _to_document_chunks(
        self,
        raw_chunks: List[dict],
        document_id: str,
        source_filename: str,
    ) -> List[DocumentChunk]:
        """
        Konversi raw chunk dicts ke DocumentChunk (untuk penyimpanan Qdrant).
        """
        doc_chunks = []
        for raw in raw_chunks:
            chunk_type = raw.get("type", "child")
            section = raw.get("section", "")
            is_parent = chunk_type == "parent"

            # Tentukan hierarchy level dan level_number dari section/type
            level_number, hierarchy_level = _infer_level(raw)

            metadata_dict = raw.get("metadata", {})
            pasal_number = metadata_dict.get("pasal")
            ayat_number = metadata_dict.get("ayat")
            pasal_rujukan = metadata_dict.get("pasal_rujukan")

            meta = ChunkMetadata(
                document_id=document_id,
                source_filename=source_filename,
                hierarchy_level=hierarchy_level,
                level_number=level_number,
                document_title=metadata_dict.get("source", ""),
                pasal_number=int(pasal_number) if isinstance(pasal_number, (int, float)) else None,
                ayat_number=int(ayat_number) if isinstance(ayat_number, (int, float)) else None,
                token_count=count_tokens(raw.get("text", "")),
                parent_chunk_id=raw.get("parent_id"),
                is_parent=is_parent,
            )

            doc_chunks.append(
                DocumentChunk(
                    chunk_id=raw["chunk_id"],
                    content=raw.get("text", ""),
                    metadata=meta,
                )
            )

        return doc_chunks


# ─────────────────────────────────────────────────────────
# MODULE-LEVEL HELPERS
# ─────────────────────────────────────────────────────────

def _to_int(value: str) -> Optional[int]:
    try:
        m = re.search(r"\d+", str(value))
        return int(m.group(0)) if m else None
    except (ValueError, TypeError):
        return None


def _get_pasal_title_without_prefix(pasal_title: str, pasal_number: str) -> str:
    """
    Ambil bagian judul setelah 'Pasal N -'.
    Contoh: 'Pasal 3 - Pelaksana Fungsi Kepolisian' → 'Pelaksana Fungsi Kepolisian'
    """
    # Hapus prefix "Pasal N - " atau "Pasal N"
    cleaned = re.sub(rf"^\s*Pasal\s+{re.escape(pasal_number)}\s*[-–]\s*", "", pasal_title)
    cleaned = re.sub(rf"^\s*Pasal\s+{re.escape(pasal_number)}\s*", "", cleaned)
    return cleaned.strip() or pasal_title.strip()


def _split_penjelasan_by_pasal(text: str) -> List[tuple]:
    """
    Pecah teks penjelasan menjadi segmen per-pasal.

    Return: list of (pasal_number_str, section_text)
    """
    # Pola: "Pasal N" menjadi pemisah section
    pattern = re.compile(r"\bPasal\s+(\d+[A-Za-z]*)\b", re.IGNORECASE)
    matches = list(pattern.finditer(text))

    if not matches:
        return []

    sections = []
    for i, m in enumerate(matches):
        pasal_number = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start:end].strip()
        if section_text:
            sections.append((pasal_number, section_text))

    return sections


def _infer_level(raw: dict):
    """Tentukan level_number dan HierarchyLevel dari raw chunk dict."""
    section = raw.get("section", "")
    chunk_type = raw.get("type", "child")
    is_parent = chunk_type == "parent"

    if section == "Konsiderans":
        return (0, HierarchyLevel.DOCUMENT) if is_parent else (1, HierarchyLevel.BAB)

    if section == "Batang Tubuh":
        if is_parent:
            return (2, HierarchyLevel.PASAL)
        else:
            metadata = raw.get("metadata", {})
            if "ayat" in metadata:
                return (3, HierarchyLevel.AYAT)
            return (2, HierarchyLevel.PASAL)

    if section == "Penjelasan":
        return (2, HierarchyLevel.PASAL) if is_parent else (3, HierarchyLevel.AYAT)

    return (1, HierarchyLevel.BAB)
