"""
app/services/knowledgebase/cleaning_service.py
=============================================
Cleaning service untuk dokumen hukum Indonesia (UU, PP, Perpres, dll.).

Pipeline:
  1. Ekstrak teks mentah dari PDF menggunakan PyMuPDF (fitz)
  2. Bersihkan artefak PDF (ligature, page numbers, header/footer berulang)
  3. Normalisasi unicode dan whitespace
  4. Parse struktur hierarki dokumen:
       - Metadata   : jenis, nomor, tahun, tentang
       - Konsiderans: Menimbang + Mengingat (dengan poin a, b, c, …)
       - Batang Tubuh: per-Pasal (dengan Ayat, Poin)
       - Penjelasan : per-Pasal yang memiliki penjelasan
  5. Kembalikan CleaningResult lengkap siap dikonsumsi ChunkingService
"""

from __future__ import annotations

import re
import logging
from pathlib import Path
from typing import Union, List, Optional, Tuple

import fitz  # PyMuPDF

from app.database.models.schemas import (
    CleaningResult,
    CleaningStatus,
    PageContent,
    BabEntry,
    PasalEntry,
    ParsedStructure,
)
from app.utils.uu_paterns import extract_uu_metadata
from app.utils.text_utils import (
    normalize_unicode,
    fix_common_pdf_artifacts,
    normalize_whitespace,
    remove_page_numbers,
    remove_header_footer_candidates,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# REGEX
# ─────────────────────────────────────────────────────────

_RE_BAB = re.compile(
    r"^\s*BAB\s+"
    r"(M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})|[IVXLCDM]+|\d+)"
    r"(?:\s+(.+))?$",
    re.IGNORECASE,
)

_RE_PASAL = re.compile(
    r"^\s*Pasal\s+(\d+[A-Za-z]?)\s*$",
    re.IGNORECASE,
)

_RE_PASAL_INLINE = re.compile(
    r"\bPasal\s+(\d+[A-Za-z]?)\b",
    re.IGNORECASE,
)

_RE_AYAT = re.compile(
    r"^\s*\((\d+)\)\s+(.+)$",
)

# Poin huruf: a. atau a)
_RE_POIN = re.compile(
    r"^\s*([a-z])\.\s+(.+)$",
)

# Poin angka: 1. atau 1)
_RE_POIN_ANGKA = re.compile(
    r"^\s*(\d+)\.\s+(.+)$",
)

_RE_MENIMBANG = re.compile(r"^\s*Menimbang\s*:", re.IGNORECASE)
_RE_MENGINGAT = re.compile(r"^\s*Mengingat\s*:", re.IGNORECASE)
_RE_MEMUTUSKAN = re.compile(r"^\s*MEMUTUSKAN\s*:", re.IGNORECASE)
_RE_PENJELASAN = re.compile(r"^\s*PENJELASAN\b", re.IGNORECASE)
_RE_PENJELASAN_PASAL = re.compile(r"\bPasal\s+(\d+[A-Za-z]?)\b", re.IGNORECASE)

_RE_PAGE_MARKER = re.compile(r"---\s*PAGE\s*\d+\s*---", re.IGNORECASE)


# ─────────────────────────────────────────────────────────
# SERVICE
# ─────────────────────────────────────────────────────────

class CleaningService:
    """
    Bersihkan dan parsing dokumen hukum Indonesia dari file PDF.

    Hasil:
      - CleaningResult.full_cleaned_text  → teks bersih lengkap
      - CleaningResult.parsed_structure   → BabEntry + PasalEntry terdeteksi
      - CleaningResult.metadata           → jenis, nomor, tahun, tentang, source_label
      - CleaningResult.konsiderans        → dict {menimbang: [...], mengingat: str}
      - CleaningResult.penjelasan_text    → teks bagian penjelasan (jika ada)
    """

    # ── Public API ─────────────────────────────────────────

    def clean_from_path(self, pdf_path: Union[str, Path]) -> CleaningResult:
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"File tidak ditemukan: {pdf_path}")
        logger.info(f"[CLEANING] Memproses file: {pdf_path.name}")
        pdf_bytes = pdf_path.read_bytes()
        return self.clean_from_bytes(pdf_bytes, source_filename=pdf_path.name)

    def clean_from_bytes(
        self, pdf_bytes: bytes, source_filename: str = "document.pdf"
    ) -> CleaningResult:
        logger.info(f"[CLEANING] Memulai: {source_filename} ({len(pdf_bytes):,} bytes)")
        result = CleaningResult(source_filename=source_filename, total_pages=0)
        try:
            pages = self._extract_pages(pdf_bytes)
            result.total_pages = len(pages)
            result.cleaned_pages = pages

            full_text = self._join_pages(pages)
            result.full_cleaned_text = full_text

            result.metadata = extract_uu_metadata(full_text)
            self._enrich_metadata(result.metadata, source_filename)

            parsed = self._parse_structure(full_text)
            result.parsed_structure = parsed["structure"]

            # Simpan data tambahan sebagai atribut dinamis agar mudah diakses
            # oleh ChunkingService tanpa mengubah schema utama.
            result.__dict__["konsiderans"] = parsed["konsiderans"]
            result.__dict__["penjelasan_text"] = parsed["penjelasan_text"]
            result.__dict__["pasal_data"] = parsed["pasal_data"]

            result.status = CleaningStatus.SUCCESS
            logger.info(
                f"[CLEANING] Selesai: {len(pages)} halaman, "
                f"{len(parsed['structure'].pasal_list)} pasal, "
                f"konsiderans={'ya' if parsed['konsiderans']['menimbang'] else 'tidak'}, "
                f"penjelasan={'ya' if parsed['penjelasan_text'] else 'tidak'}"
            )
        except Exception as e:
            logger.error(f"[CLEANING] Gagal: {e}", exc_info=True)
            result.status = CleaningStatus.FAILED
            result.issues.append(str(e))
        return result

    # ── PDF Extraction ─────────────────────────────────────

    def _extract_pages(self, pdf_bytes: bytes) -> List[PageContent]:
        """Ekstrak teks per halaman menggunakan PyMuPDF lalu bersihkan."""
        pages: List[PageContent] = []
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for i in range(len(doc)):
            page = doc.load_page(i)
            raw_text = page.get_text("text")
            cleaned = self._clean_page_text(raw_text)
            pages.append(
                PageContent(
                    page_number=i + 1,
                    raw_text=raw_text,
                    cleaned_text=cleaned,
                    word_count=len(cleaned.split()),
                    char_count=len(cleaned),
                )
            )
        doc.close()
        return pages

    def _clean_page_text(self, text: str) -> str:
        """Bersihkan satu halaman teks dari artefak umum PDF."""
        text = normalize_unicode(text)
        text = fix_common_pdf_artifacts(text)
        text = remove_page_numbers(text)
        text = normalize_whitespace(text)
        return text

    def _join_pages(self, pages: List[PageContent]) -> str:
        """Gabungkan semua halaman, hilangkan header/footer berulang."""
        all_lines: List[str] = []
        for p in pages:
            all_lines.extend(p.cleaned_text.split("\n"))

        filtered = remove_header_footer_candidates(all_lines, threshold=3)
        full_text = "\n".join(filtered)
        # Hilangkan page marker jika ada
        full_text = _RE_PAGE_MARKER.sub("", full_text)
        return normalize_whitespace(full_text)

    # ── Metadata ───────────────────────────────────────────

    def _enrich_metadata(self, metadata: dict, source_filename: str) -> None:
        """Tambahkan label source yang rapi ke metadata."""
        jenis = metadata.get("jenis", "UU")
        nomor = metadata.get("nomor", "")
        tahun = metadata.get("tahun", "")
        if nomor and tahun:
            metadata["source_label"] = f"{jenis} No {nomor} Tahun {tahun}"
        else:
            # fallback ke nama file
            metadata["source_label"] = source_filename.replace(".pdf", "").replace("_", " ")

    # ── Structure Parsing ──────────────────────────────────

    def _parse_structure(self, text: str) -> dict:
        """
        Parse hierarki dokumen hukum Indonesia dari teks bersih.

        Return:
            {
              "structure": ParsedStructure,
              "konsiderans": {"menimbang": [...], "mengingat": str},
              "penjelasan_text": str,
              "pasal_data": [dict per pasal lengkap],
            }
        """
        lines = text.split("\n")

        # ── 1. Pisahkan zona dokumen ───────────────────────
        konsiderans_start, batang_start, penjelasan_start = self._detect_zones(lines)

        # ── 2. Parse Konsiderans ───────────────────────────
        konsiderans = self._parse_konsiderans(
            lines[konsiderans_start:batang_start]
        )

        # ── 3. Parse Batang Tubuh ──────────────────────────
        batang_end = penjelasan_start if penjelasan_start < len(lines) else len(lines)
        bab_list, pasal_list, pasal_data = self._parse_batang_tubuh(
            lines[batang_start:batang_end],
            offset=batang_start,
            full_text=text,
        )

        # ── 4. Ambil teks Penjelasan ───────────────────────
        penjelasan_text = ""
        if penjelasan_start < len(lines):
            penjelasan_text = "\n".join(lines[penjelasan_start:]).strip()

        structure = ParsedStructure(
            bab_list=bab_list,
            pasal_list=pasal_list,
            total_bab=len(bab_list),
            total_pasal=len(pasal_list),
        )

        return {
            "structure": structure,
            "konsiderans": konsiderans,
            "penjelasan_text": penjelasan_text,
            "pasal_data": pasal_data,
        }

    # ── Zone Detection ─────────────────────────────────────

    def _detect_zones(self, lines: List[str]) -> Tuple[int, int, int]:
        """
        Deteksi batas zona dokumen: konsiderans, batang tubuh, penjelasan.

        Return:
            (konsiderans_start_line, batang_start_line, penjelasan_start_line)
        """
        konsiderans_start = 0
        batang_start = 0
        penjelasan_start = len(lines)

        for i, line in enumerate(lines):
            stripped = line.strip()

            if konsiderans_start == 0 and (
                _RE_MENIMBANG.match(stripped) or
                re.match(r"^\s*Menimbang\b", stripped, re.IGNORECASE)
            ):
                konsiderans_start = i

            if _RE_MEMUTUSKAN.match(stripped):
                batang_start = i
                continue

            if batang_start == 0 and re.match(r"^\s*BAB\s+I\b", stripped, re.IGNORECASE):
                batang_start = i
                continue

            if batang_start == 0 and _RE_PASAL.match(stripped):
                batang_start = i
                continue

            if _RE_PENJELASAN.match(stripped) and batang_start > 0:
                penjelasan_start = i
                break

        return konsiderans_start, batang_start, penjelasan_start

    # ── Konsiderans ────────────────────────────────────────

    def _parse_konsiderans(self, lines: List[str]) -> dict:
        """
        Parse bagian Menimbang dan Mengingat.

        Return:
            {
              "menimbang": [{"huruf": "a", "text": "..."}, ...],
              "mengingat": "teks mengingat...",
              "full_text": "teks gabungan konsiderans",
            }
        """
        menimbang_items: list = []
        mengingat_parts: list = []
        full_parts: list = []

        zone = "preamble"  # preamble | menimbang | mengingat
        current_poin: Optional[dict] = None

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            full_parts.append(stripped)

            if _RE_MENIMBANG.match(stripped) or re.match(r"^Menimbang\b", stripped, re.IGNORECASE):
                zone = "menimbang"
                continue

            if _RE_MENGINGAT.match(stripped) or re.match(r"^Mengingat\b", stripped, re.IGNORECASE):
                # Simpan poin terakhir menimbang
                if current_poin:
                    menimbang_items.append(current_poin)
                    current_poin = None
                zone = "mengingat"
                continue

            if zone == "menimbang":
                m = _RE_POIN.match(stripped)
                if m:
                    if current_poin:
                        menimbang_items.append(current_poin)
                    current_poin = {"huruf": m.group(1), "text": m.group(2).strip()}
                elif current_poin:
                    current_poin["text"] += " " + stripped

            elif zone == "mengingat":
                mengingat_parts.append(stripped)

        if current_poin:
            menimbang_items.append(current_poin)

        return {
            "menimbang": menimbang_items,
            "mengingat": " ".join(mengingat_parts),
            "full_text": "\n".join(full_parts),
        }

    # ── Batang Tubuh ───────────────────────────────────────

    def _parse_batang_tubuh(
        self,
        lines: List[str],
        offset: int,
        full_text: str,
    ) -> Tuple[List[BabEntry], List[PasalEntry], List[dict]]:
        """
        Parse BAB dan Pasal dari zona Batang Tubuh.

        Return:
            (bab_list, pasal_list, pasal_data)

        pasal_data adalah list dict detail tiap pasal:
            {
              "pasal_number": str,
              "title": str,
              "section": "Batang Tubuh",
              "bab_number": str,
              "bab_title": str,
              "full_text": str,           ← teks pasal lengkap
              "ayat_list": [...],         ← list ayat + poin
              "char_start": int,
            }
        """
        bab_list: List[BabEntry] = []
        pasal_list: List[PasalEntry] = []
        pasal_data: List[dict] = []

        current_bab: dict = {"number": "", "title": "", "full_header": "", "char_start": 0}
        current_pasal: Optional[dict] = None
        current_pasal_lines: List[str] = []

        def _flush_pasal():
            nonlocal current_pasal, current_pasal_lines
            if current_pasal is None:
                return
            pasal_text = "\n".join(current_pasal_lines).strip()
            ayat_list = _extract_ayats(pasal_text, current_pasal["pasal_number"])
            pasal_title = _build_pasal_title(current_pasal["pasal_number"], pasal_text)
            current_pasal.update({
                "full_text": pasal_text,
                "ayat_list": ayat_list,
                "title": pasal_title,
            })
            pasal_data.append(current_pasal)

            pasal_list.append(PasalEntry(
                number=current_pasal["pasal_number"],
                full_header=f"Pasal {current_pasal['pasal_number']}",
                char_start=current_pasal["char_start"],
                bab_number=current_pasal.get("bab_number"),
                ayat_count=len(ayat_list),
            ))
            current_pasal = None
            current_pasal_lines = []

        # Hitung char_start dengan cara mencari posisi dalam full_text
        # kita cache posisi searching
        search_from = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                if current_pasal is not None:
                    current_pasal_lines.append("")
                continue

            # ── Deteksi BAB ─────────────────────────────
            m_bab = _RE_BAB.match(stripped)
            if m_bab:
                _flush_pasal()
                bab_number = m_bab.group(1).upper()
                # Judul bab biasanya di baris berikutnya; ambil dari group 2 jika ada
                bab_title_inline = (m_bab.group(2) or "").strip().upper()

                # Coba ambil judul dari baris berikut jika inline kosong
                bab_title = bab_title_inline
                if not bab_title and i + 1 < len(lines):
                    next_line = lines[i + 1].strip().upper()
                    if next_line and not _RE_PASAL.match(next_line) and not _RE_BAB.match(next_line):
                        bab_title = next_line

                char_start_bab = self._find_char_pos(full_text, stripped, search_from)
                full_header = f"BAB {bab_number}"
                if bab_title:
                    full_header += f"\n{bab_title}"

                current_bab = {
                    "number": bab_number,
                    "title": bab_title,
                    "full_header": full_header,
                    "char_start": char_start_bab,
                }
                bab_list.append(BabEntry(
                    number=bab_number,
                    title=bab_title,
                    full_header=full_header,
                    char_start=char_start_bab,
                ))
                search_from = max(0, char_start_bab)
                continue

            # ── Deteksi Pasal ────────────────────────────
            m_pasal = _RE_PASAL.match(stripped)
            if m_pasal:
                _flush_pasal()
                pasal_number = m_pasal.group(1)
                char_start_pasal = self._find_char_pos(full_text, stripped, search_from)
                current_pasal = {
                    "pasal_number": pasal_number,
                    "section": "Batang Tubuh",
                    "bab_number": current_bab.get("number", ""),
                    "bab_title": current_bab.get("title", ""),
                    "char_start": char_start_pasal,
                }
                current_pasal_lines = [stripped]
                search_from = max(0, char_start_pasal)
                continue

            # ── Konten pasal ─────────────────────────────
            if current_pasal is not None:
                current_pasal_lines.append(stripped)

        _flush_pasal()
        return bab_list, pasal_list, pasal_data

    # ── Helpers ────────────────────────────────────────────

    @staticmethod
    def _find_char_pos(text: str, target: str, start_from: int = 0) -> int:
        """Cari posisi karakter dari target dalam text mulai dari start_from."""
        idx = text.find(target, start_from)
        return max(idx, 0)


# ─────────────────────────────────────────────────────────
# HELPER FUNCTIONS (module-level agar mudah ditest)
# ─────────────────────────────────────────────────────────

def _extract_ayats(pasal_text: str, pasal_number: str) -> List[dict]:
    """
    Ekstrak daftar ayat dari teks pasal.
    Jika tidak ada ayat bernomor, kembalikan satu entri 'tunggal'.

    Return list of:
        {"ayat_number": int | "tunggal", "text": str, "poin_list": [...]}
    """
    lines = pasal_text.split("\n")
    ayat_matches = []
    for i, line in enumerate(lines):
        m = _RE_AYAT.match(line.strip())
        if m:
            ayat_matches.append((i, int(m.group(1)), line.strip()))

    if not ayat_matches:
        # Pasal tunggal, cek apakah ada poin huruf
        poin_list = _extract_poin_list(pasal_text)
        return [{"ayat_number": "tunggal", "text": pasal_text.strip(), "poin_list": poin_list}]

    ayats = []
    for idx, (line_idx, ayat_num, _) in enumerate(ayat_matches):
        next_line_idx = ayat_matches[idx + 1][0] if idx + 1 < len(ayat_matches) else len(lines)
        ayat_lines = lines[line_idx:next_line_idx]
        ayat_text = "\n".join(l.strip() for l in ayat_lines if l.strip())
        poin_list = _extract_poin_list(ayat_text)
        ayats.append({
            "ayat_number": ayat_num,
            "text": ayat_text,
            "poin_list": poin_list,
        })
    return ayats


def _extract_poin_list(text: str) -> List[dict]:
    """Ekstrak poin-poin huruf (a., b., c.) dari teks ayat."""
    poin_list = []
    current: Optional[dict] = None
    for line in text.split("\n"):
        stripped = line.strip()
        m = _RE_POIN.match(stripped)
        if m:
            if current:
                poin_list.append(current)
            current = {"huruf": m.group(1), "text": m.group(2).strip()}
        elif current and stripped:
            current["text"] += " " + stripped
    if current:
        poin_list.append(current)
    return poin_list


def _build_pasal_title(pasal_number: str, pasal_text: str) -> str:
    """
    Coba bangun judul deskriptif untuk pasal dari kontennya.
    Fallback ke 'Pasal {nomor}'.
    """
    # Ambil baris non-pasal pertama sebagai sinopsi
    for line in pasal_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(rf"^\s*Pasal\s+{pasal_number}\s*$", stripped, re.IGNORECASE):
            continue
        if re.match(r"^\s*\(\d+\)", stripped):
            # Ambil sedikit dari isi ayat pertama
            snippet = re.sub(r"^\s*\(\d+\)\s*", "", stripped)
            # Potong di 60 karakter pertama dan gunakan sebagai judul ringkas
            return f"Pasal {pasal_number} - {snippet[:60].rstrip()}"
        # Baris non-header → jadikan judul
        if len(stripped) < 80 and not re.match(r"^\s*[a-z]\.\s", stripped):
            return f"Pasal {pasal_number} - {stripped[:60]}"
    return f"Pasal {pasal_number}"
