"""
SERVICE: Cleaning Service (Rule-Based)
=======================================
Pipeline pembersihan dokumen PDF UU Indonesia menggunakan
pendekatan rule-based/regex murni tanpa LLM.

Pipeline (5 tahap):
  1. Ekstraksi teks mentah per halaman      (PyMuPDF)
  2. Cleaning per halaman                   (hapus noise, perbaiki OCR artifact)
  3. Gabung halaman + cleaning pasca-gabung (normalisasi struktur UU)
  4. Ekstraksi metadata                     (nomor, tahun, tentang, jenis UU)
  5. Pra-parsing struktur hierarki          (deteksi & peta BAB, Pasal, Ayat)

Output: CleaningResult berisi teks bersih + metadata + parsed_structure,
        siap langsung dipakai oleh ChunkingService.
"""

import re
import logging
from pathlib import Path
from typing import Union, List, Optional, Tuple
from collections import Counter

import fitz  # PyMuPDF

from app.models.schemas import (
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
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# REGEX PATTERNS — PER-PAGE CLEANING
# ═══════════════════════════════════════════════════════════════

# URL/domain JDIH dan sumber hukum online yang sering muncul di footer
_RE_JDIH_URL = re.compile(
    r"(?:www\.)?jdih(?:\.\w+)+\.go\.id"
    r"|peraturan\.go\.id"
    r"|lnri\.co\.id"
    r"|ditjenpp\.kemenkumham\.go\.id",
    re.IGNORECASE,
)

# Format nomor halaman yang umum ditemukan di dokumen UU Indonesia
_RE_PAGE_NUM_FORMATS = [
    re.compile(r"^\s*-\s*\d+\s*-\s*$"),                        # - 5 -
    re.compile(r"^\s*\d+\s*$"),                                  # 5
    re.compile(r"^\s*Halaman\s+\d+\s+(?:dari|of)\s+\d+\s*$", re.IGNORECASE),  # Halaman 5 dari 20
    re.compile(r"^\s*Halaman\s+\d+\s*$", re.IGNORECASE),        # Halaman 5
    re.compile(r"^\s*Page\s+\d+\s*$", re.IGNORECASE),           # Page 5
    re.compile(r"^\s*\d+\s*/\s*\d+\s*$"),                       # 5/20
]

# Kata terputus oleh hyphen di akhir baris: "pemeri-\ntah" → "pemerintah"
# Kecuali kata majemuk yang memang pakai tanda hubung: "undang-\nundang"
_RE_HYPHEN_LINEBREAK = re.compile(r"([A-Za-z])-\n([a-z])")

# Karakter terpencar akibat OCR: "d e n g a n" → "dengan"
# Heuristik: minimal 3 huruf tunggal dipisah spasi
_RE_SPACED_CHARS = re.compile(r"\b([A-Za-z])((?:\s[A-Za-z]){2,})\b")

# Substitusi OCR umum (pola → teks yang benar)
_OCR_FIXES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\bPasa[l1]\b"),                    "Pasal"),
    (re.compile(r"\b1ndonesia\b", re.IGNORECASE),    "Indonesia"),
    (re.compile(r"\bIndonesla\b", re.IGNORECASE),    "Indonesia"),
    (re.compile(r"\bRep[ub]blik\b", re.IGNORECASE),  "Republik"),
    (re.compile(r"\btah[vu]n\b", re.IGNORECASE),     "tahun"),
    (re.compile(r"\bden[gq]an\b", re.IGNORECASE),    "dengan"),
    (re.compile(r"\bpemer[il]ntah\b", re.IGNORECASE),"pemerintah"),
    (re.compile(r"\bUndang[-\s]?[Uu]ndang\b"),       "Undang-Undang"),
    (re.compile(r"\bpasa[l1]\b", re.IGNORECASE),     "pasal"),
    (re.compile(r"\baya[t7]\b", re.IGNORECASE),      "ayat"),
    (re.compile(r"\bhu[rk]uf\b", re.IGNORECASE),     "huruf"),
]


# ═══════════════════════════════════════════════════════════════
# REGEX PATTERNS — POST-JOIN NORMALISASI STRUKTUR UU
# ═══════════════════════════════════════════════════════════════

# BAB header: "BAB I", "BAB II", "BAB X", dsb.
_RE_BAB_HEADER = re.compile(
    r"(?<!\w)(BAB\s+"
    r"(?:M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"
    r"|[IVXLCDM]+"
    r"|\d+)"
    r")(?!\w)",
    re.IGNORECASE,
)

# Pasal header: "Pasal 1", "Pasal 3A", dsb.
_RE_PASAL_HEADER = re.compile(
    r"(?<!\w)(Pasal\s+\d+[A-Za-z]?)(?!\w)",
    re.IGNORECASE,
)

# Bagian header: "Bagian Kesatu", "Bagian Pertama", dsb.
_RE_BAGIAN_HEADER = re.compile(
    r"(?<!\w)(Bagian\s+"
    r"(?:Kesatu|Kedua|Ketiga|Keempat|Kelima|Keenam|Ketujuh|"
    r"Kedelapan|Kesembilan|Kesepuluh|Pertama|[IVXLCDM]+|\d+)"
    r")(?!\w)",
    re.IGNORECASE,
)

# Paragraf/Ayat: "(1)", "(2)", dsb. di tengah baris
_RE_AYAT_INLINE = re.compile(r"(?<!\n)\s*(\(\d+\))\s+")

# Lebih dari 2 baris kosong berturut-turut
_RE_EXCESS_NEWLINES = re.compile(r"\n{3,}")


# ═══════════════════════════════════════════════════════════════
# REGEX PATTERNS — PRA-PARSING STRUKTUR
# ═══════════════════════════════════════════════════════════════

# Mendeteksi BAB beserta nomornya (group 1) dan judul inline-nya (group 2, opsional)
_RE_PARSE_BAB = re.compile(
    r"(?:^|\n)\s*(BAB\s+"
    r"(M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"
    r"|[IVXLCDM]+"
    r"|\d+)"
    r"(?:\s+([^\n]+))?)\s*(?:\n|$)",
    re.IGNORECASE | re.MULTILINE,
)

# Mendeteksi Pasal beserta nomornya (group 1)
_RE_PARSE_PASAL = re.compile(
    r"(?:^|\n)\s*(Pasal\s+(\d+[A-Za-z]?))\s*(?:\n|$)",
    re.IGNORECASE | re.MULTILINE,
)

# Mendeteksi marker Ayat "(N)" di awal baris
_RE_PARSE_AYAT = re.compile(r"^\s*\(\d+\)\s+", re.MULTILINE)


# ═══════════════════════════════════════════════════════════════
# CLEANING SERVICE
# ═══════════════════════════════════════════════════════════════

class CleaningService:
    """
    Service pembersih dokumen PDF UU Indonesia.

    Menggunakan pipeline rule-based/regex murni (tanpa LLM/API eksternal).
    Hasilnya adalah CleaningResult yang siap dipakai oleh ChunkingService.

    Penggunaan:
        service = CleaningService()
        result  = service.clean_from_path("path/ke/uu.pdf")
        # atau
        result  = service.clean_from_bytes(pdf_bytes, "uu.pdf")
    """

    # ── Public API ──────────────────────────────────────────

    def clean_from_path(self, pdf_path: Union[str, Path]) -> CleaningResult:
        """Bersihkan PDF dari file path lokal."""
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"File tidak ditemukan: {pdf_path}")

        logger.info(f"[CLEANING] Memproses file: {pdf_path.name}")
        pdf_bytes = pdf_path.read_bytes()
        return self.clean_from_bytes(pdf_bytes, source_filename=pdf_path.name)

    def clean_from_bytes(
        self, pdf_bytes: bytes, source_filename: str = "document.pdf"
    ) -> CleaningResult:
        """
        Bersihkan PDF dari raw bytes.

        Args:
            pdf_bytes:       Konten file PDF dalam bytes.
            source_filename: Nama file sumber (untuk metadata & logging).

        Returns:
            CleaningResult berisi teks bersih, metadata, dan parsed_structure.
        """
        logger.info(
            f"[CLEANING] Memulai: {source_filename} ({len(pdf_bytes):,} bytes)"
        )
        result = CleaningResult(source_filename=source_filename, total_pages=0)

        try:
            # ── Tahap 1: Ekstraksi teks mentah per halaman ──────────
            pages = self._extract_pages(pdf_bytes, result)
            result.total_pages = len(pages)
            logger.info(f"[CLEANING] Tahap 1 selesai: {result.total_pages} halaman diekstrak")

            # ── Tahap 2: Cleaning per halaman ───────────────────────
            all_raw_lines = []  # dikumpulkan untuk deteksi header/footer global
            for page in pages:
                all_raw_lines.extend(page.raw_text.split("\n"))

            # Deteksi baris yang berulang (header/footer repeating)
            repeating_lines = self._detect_repeating_lines(all_raw_lines)

            cleaned_pages = [
                self._clean_page(page, repeating_lines) for page in pages
            ]
            result.cleaned_pages = cleaned_pages
            logger.info(f"[CLEANING] Tahap 2 selesai: semua halaman dibersihkan")

            # ── Tahap 3: Gabung & post-join cleaning ────────────────
            joined = "\n\n".join(
                p.cleaned_text for p in cleaned_pages if p.cleaned_text.strip()
            )
            full_text = self._post_join_cleaning(joined)
            result.full_cleaned_text = full_text
            logger.info(
                f"[CLEANING] Tahap 3 selesai: {result.total_words:,} kata, "
                f"{len(full_text):,} karakter"
            )

            # ── Tahap 4: Ekstraksi metadata UU ──────────────────────
            result.metadata = extract_uu_metadata(full_text)
            logger.info(f"[CLEANING] Tahap 4 selesai: metadata={result.metadata}")

            # ── Tahap 5: Pra-parsing struktur hierarki ──────────────
            result.parsed_structure = self._parse_structure(full_text)
            logger.info(
                f"[CLEANING] Tahap 5 selesai: "
                f"BAB={result.parsed_structure.total_bab}, "
                f"Pasal={result.parsed_structure.total_pasal}, "
                f"Ayat={result.parsed_structure.total_ayat}"
            )

            result.status = CleaningStatus.SUCCESS
            logger.info(f"[CLEANING] ✅ Selesai: {source_filename}")

        except Exception as e:
            logger.error(f"[CLEANING] ❌ Error fatal: {e}", exc_info=True)
            result.status = CleaningStatus.FAILED
            result.issues.append(str(e))
            raise

        return result

    # ── Tahap 1: Ekstraksi halaman ──────────────────────────────────

    def _extract_pages(
        self, pdf_bytes: bytes, result: CleaningResult
    ) -> List[PageContent]:
        """
        Ekstrak teks mentah dari setiap halaman PDF menggunakan PyMuPDF.
        Halaman kosong (gambar/scan) dicatat sebagai issues.
        """
        pages: List[PageContent] = []
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        for i in range(len(doc)):
            page = doc[i]
            # TEXT_PRESERVE_LIGATURES: gabungkan ligatur (fi, fl)
            # TEXT_PRESERVE_WHITESPACE: pertahankan spasi asli
            raw_text = page.get_text(
                "text",
                flags=fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE,
            )

            if not raw_text.strip():
                msg = (
                    f"Halaman {i + 1} tidak mengandung teks yang dapat diekstrak "
                    f"(kemungkinan gambar/scan)."
                )
                result.issues.append(msg)
                logger.warning(f"[CLEANING] {msg}")

            pages.append(PageContent(page_number=i + 1, raw_text=raw_text))

        doc.close()
        return pages

    # ── Tahap 2: Cleaning per halaman ──────────────────────────────

    def _detect_repeating_lines(
        self, all_lines: List[str], threshold: int = 3
    ) -> set:
        """
        Deteksi baris yang muncul berulang kali di seluruh dokumen —
        kemungkinan besar header/footer (mis: nama instansi, alamat web).

        Args:
            all_lines: Semua baris dari semua halaman.
            threshold: Minimal berapa kali sebuah baris harus muncul agar dianggap header/footer.

        Returns:
            Set string yang dianggap header/footer dan perlu dihapus.
        """
        stripped = [l.strip() for l in all_lines]
        counts = Counter(s for s in stripped if len(s) > 3)  # abaikan baris sangat pendek
        return {line for line, count in counts.items() if count >= threshold}

    def _clean_page(
        self, page: PageContent, repeating_lines: set
    ) -> PageContent:
        """
        Terapkan pipeline cleaning lengkap pada satu halaman.

        Langkah:
          a. Normalisasi Unicode & PDF artifacts
          b. Hapus header/footer berulang
          c. Hapus baris nomor halaman
          d. Hapus URL JDIH dan sejenisnya
          e. Perbaiki kata terputus (hyphen break)
          f. Perbaiki karakter terpencar OCR (spaced chars)
          g. Terapkan koreksi OCR
          h. Normalisasi whitespace
        """
        text = page.raw_text

        if not text.strip():
            page.cleaned_text = ""
            return page

        # 2a. Normalisasi Unicode & PDF artifacts (ligatur, soft-hyphen, dll.)
        text = normalize_unicode(text)
        text = fix_common_pdf_artifacts(text)

        # 2b. Hapus baris yang teridentifikasi sebagai header/footer berulang
        lines = text.split("\n")
        lines = [l for l in lines if l.strip() not in repeating_lines]
        text = "\n".join(lines)

        # 2c. Hapus baris nomor halaman
        lines = text.split("\n")
        filtered_lines = []
        for line in lines:
            stripped = line.strip()
            if any(pat.match(stripped) for pat in _RE_PAGE_NUM_FORMATS):
                continue
            filtered_lines.append(line)
        text = "\n".join(filtered_lines)

        # 2d. Hapus URL JDIH dan domain hukum
        lines = text.split("\n")
        lines = [
            l for l in lines
            if not _RE_JDIH_URL.search(l.strip())
            or len(l.strip()) > len(_RE_JDIH_URL.search(l.strip()).group(0)) + 20
        ]
        text = "\n".join(lines)

        # 2e. Perbaiki kata terputus oleh hyphen di akhir baris
        # "pemeri-\ntah" → "pemerintah", "un-\ndang" → "undang"
        text = _RE_HYPHEN_LINEBREAK.sub(r"\1\2", text)

        # 2f. Perbaiki karakter terpencar: "d e n g a n" → "dengan"
        text = self._fix_spaced_chars(text)

        # 2g. Koreksi substitusi OCR umum
        for pattern, replacement in _OCR_FIXES:
            text = pattern.sub(replacement, text)

        # 2h. Normalisasi whitespace (spasi ganda, trailing space, blank lines)
        text = normalize_whitespace(text)

        page.cleaned_text = text
        page.word_count = len(text.split())
        page.char_count = len(text)
        return page

    def _fix_spaced_chars(self, text: str) -> str:
        """
        Perbaiki karakter yang dipisah spasi akibat OCR artifact.
        Contoh: "d e n g a n" → "dengan", "P a s a l" → "Pasal"

        Menggunakan heuristik: minimal 3 huruf tunggal berurutan dipisah spasi.
        """
        def merge_match(m: re.Match) -> str:
            return m.group(0).replace(" ", "")

        return _RE_SPACED_CHARS.sub(merge_match, text)

    # ── Tahap 3: Post-join cleaning ────────────────────────────────

    def _post_join_cleaning(self, text: str) -> str:
        """
        Cleaning lanjutan setelah semua halaman digabung.
        Tujuan: menormalisasi format struktur UU agar konsisten.

        Langkah:
          a. Normalisasi BAB header (pastikan di baris tersendiri + spasi sebelumnya)
          b. Normalisasi Pasal header (pastikan di baris tersendiri)
          c. Normalisasi Bagian header
          d. Normalisasi marker Ayat (pindahkan ke baris baru jika inline)
          e. Bersihkan blank lines berlebih (maks. 2 baris kosong)
        """
        # 3a. BAB header → pastikan ada baris kosong sebelumnya
        text = _RE_BAB_HEADER.sub(
            lambda m: f"\n\n{m.group(1).upper()}", text
        )

        # 3b. Pasal header → pastikan di baris sendiri
        text = _RE_PASAL_HEADER.sub(
            lambda m: f"\n\n{m.group(1).capitalize().replace('Pasal', 'Pasal')}\n",
            text,
        )

        # Normalisasi ulang "Pasal" agar konsisten kapitalisasi
        text = re.sub(r"\b(PASAL)\b", "Pasal", text)

        # 3c. Bagian header → pastikan di baris tersendiri
        text = _RE_BAGIAN_HEADER.sub(
            lambda m: f"\n\n{m.group(1)}", text
        )

        # 3d. Ayat inline → pindahkan ke awal baris baru
        # "(1) Pemerintah...bla. (2) Dalam..." → pisah jadi baris baru
        text = _RE_AYAT_INLINE.sub(lambda m: f"\n{m.group(1)} ", text)

        # 3e. Bersihkan blank lines berlebih
        text = _RE_EXCESS_NEWLINES.sub("\n\n", text)

        return text.strip()

    # ── Tahap 5: Pra-parsing struktur hierarki ─────────────────────

    def _parse_structure(self, text: str) -> ParsedStructure:
        """
        Pra-parsing teks bersih untuk mendeteksi dan memetakan struktur
        hierarki dokumen UU: BAB → Pasal → Ayat.

        Returns:
            ParsedStructure berisi:
            - bab_list  : daftar BAB dengan posisi, judul, dan jumlah Pasal
            - pasal_list: daftar Pasal dengan posisi, BAB induk, dan jumlah Ayat
            - total_*   : ringkasan jumlah masing-masing level
        """
        bab_list: List[BabEntry] = []
        pasal_list: List[PasalEntry] = []

        # ── 5.1 Deteksi semua BAB ─────────────────────────────────
        for m in _RE_PARSE_BAB.finditer(text):
            number = m.group(2).strip().upper()
            title_inline = (m.group(3) or "").strip().upper()

            # Jika judul tidak ada inline, ambil dari baris berikutnya
            title = title_inline
            if not title:
                after = text[m.end():m.end() + 200]
                next_line = after.lstrip("\n").split("\n")[0].strip()
                # Judul BAB biasanya kapital semua dan bukan header lain
                if (
                    next_line
                    and next_line.isupper()
                    and not re.match(r"^(BAB|PASAL|BAGIAN)\b", next_line, re.IGNORECASE)
                ):
                    title = next_line

            full_header = f"BAB {number}" + (f"\n{title}" if title else "")

            bab_list.append(
                BabEntry(
                    number=number,
                    title=title,
                    full_header=full_header,
                    char_start=m.start(),
                )
            )

        # ── 5.2 Deteksi semua Pasal ───────────────────────────────
        pasal_matches = list(_RE_PARSE_PASAL.finditer(text))
        for idx, m in enumerate(pasal_matches):
            number = m.group(2).strip()
            full_header = f"Pasal {number}"
            char_start = m.start()

            # Tentukan BAB induk: BAB terakhir yang posisinya ≤ posisi Pasal ini
            bab_context: Optional[str] = None
            for bab in reversed(bab_list):
                if bab.char_start <= char_start:
                    bab_context = bab.number
                    break

            # Hitung Ayat dalam Pasal ini
            # Batas akhir: awal Pasal berikutnya, atau akhir teks
            pasal_end = (
                pasal_matches[idx + 1].start()
                if idx + 1 < len(pasal_matches)
                else len(text)
            )
            pasal_text = text[char_start:pasal_end]
            ayat_count = len(_RE_PARSE_AYAT.findall(pasal_text))

            pasal_list.append(
                PasalEntry(
                    number=number,
                    full_header=full_header,
                    char_start=char_start,
                    bab_number=bab_context,
                    ayat_count=ayat_count,
                )
            )

        # ── 5.3 Hitung Pasal per BAB ──────────────────────────────
        bab_positions = [(b.char_start, b.number) for b in bab_list]
        for i, bab in enumerate(bab_list):
            # Batas akhir BAB ini = awal BAB berikutnya, atau akhir teks
            bab_end = bab_positions[i + 1][0] if i + 1 < len(bab_positions) else len(text)

            bab_pasals = [
                p for p in pasal_list
                if bab.char_start <= p.char_start < bab_end
            ]
            bab.pasal_count = len(bab_pasals)

            if bab_pasals:
                first_num = bab_pasals[0].number
                last_num  = bab_pasals[-1].number
                bab.pasal_start = int(first_num) if first_num.isdigit() else None
                bab.pasal_end   = int(last_num)  if last_num.isdigit()  else None

        total_ayat = sum(p.ayat_count for p in pasal_list)

        logger.info(
            f"[PARSING] Ditemukan: {len(bab_list)} BAB, "
            f"{len(pasal_list)} Pasal, {total_ayat} Ayat"
        )

        return ParsedStructure(
            bab_list=bab_list,
            pasal_list=pasal_list,
            total_bab=len(bab_list),
            total_pasal=len(pasal_list),
            total_ayat=total_ayat,
        )