"""
SERVICE: Cleaning Service
=========================
Bertanggung jawab untuk:
1. Mengekstrak teks mentah dari file PDF menggunakan PyMuPDF (fitz)
2. Membersihkan artefak PDF (encoding, ligature, layout artifacts)
3. Menghapus header/footer berulang
4. Menormalisasi whitespace dan format teks
5. Menghasilkan CleaningResult yang siap diproses chunking
"""

from pathlib import Path
from typing import Union
import logging
import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

from app.models.schemas import CleaningResult, CleaningStatus, PageContent
from app.utils.text_utils import (
    normalize_unicode,
    fix_common_pdf_artifacts,
    normalize_whitespace,
    remove_page_numbers,
    remove_header_footer_candidates,
)
from app.utils.uu_patterns import extract_uu_metadata
from app.config import settings


class CleaningService:
    """
    Service untuk membersihkan dokumen PDF undang-undang.
    Library: PyMuPDF (fitz)

    Pipeline:
        PDF bytes/path
            → ekstraksi teks per halaman (PyMuPDF)
            → fix encoding & unicode
            → fix PDF artifacts (ligature, soft-hyphen)
            → hapus nomor halaman
            → deteksi & hapus header/footer berulang
            → normalisasi whitespace
            → gabung jadi full text
            → ekstrak metadata UU
    """

    def __init__(self):
        self._header_footer_threshold = 3  # muncul ≥3x → anggap header/footer

    # ─────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────────

    async def clean_from_path(self, pdf_path: Union[str, Path]) -> CleaningResult:
        """Bersihkan PDF dari file path."""
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"File tidak ditemukan: {pdf_path}")

        logger.info(f"[CLEANING] Memproses file: {pdf_path.name}")
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        return await self.clean_from_bytes(pdf_bytes, source_filename=pdf_path.name)

    async def clean_from_bytes(
        self, pdf_bytes: bytes, source_filename: str = "document.pdf"
    ) -> CleaningResult:
        """Bersihkan PDF dari bytes (untuk upload via API)."""
        logger.info(f"[CLEANING] Memulai cleaning: {source_filename} ({len(pdf_bytes):,} bytes)")

        result = CleaningResult(
            source_filename=source_filename,
            total_pages=0,
        )

        try:
            # Step 1: Buka PDF dan ekstrak teks per halaman
            pages = self._extract_pages(pdf_bytes, result)
            result.total_pages = len(pages)
            logger.info(f"[CLEANING] Diekstrak {result.total_pages} halaman")

            # Step 2: Cleaning per halaman
            cleaned_pages = [self._clean_page(page) for page in pages]

            # Step 3: Hapus header/footer berulang lintas halaman
            cleaned_pages = self._remove_cross_page_artifacts(cleaned_pages)

            result.cleaned_pages = cleaned_pages

            # Step 4: Gabung semua halaman
            full_text = self._merge_pages(cleaned_pages)
            result.full_cleaned_text = full_text

            # Step 5: Ekstrak metadata UU dari teks
            result.metadata = extract_uu_metadata(full_text)

            logger.info(
                f"[CLEANING] Selesai: {result.total_pages} hal, "
                f"{result.total_words:,} kata, "
                f"metadata={result.metadata}"
            )
            result.status = CleaningStatus.SUCCESS

        except Exception as e:
            logger.error(f"[CLEANING] Error: {e}")
            result.status = CleaningStatus.FAILED
            result.issues.append(str(e))
            raise

        return result

    # ─────────────────────────────────────────────────────────────────
    # STEP 1: EKSTRAKSI TEKS
    # ─────────────────────────────────────────────────────────────────

    def _extract_pages(self, pdf_bytes: bytes, result: CleaningResult) -> list[PageContent]:
        """Ekstrak teks dari setiap halaman PDF menggunakan PyMuPDF."""
        pages = []
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        for page_num in range(len(doc)):
            page = doc[page_num]

            # Ekstrak dengan flag untuk preservasi layout
            raw_text = page.get_text("text", flags=fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE)

            if not raw_text.strip():
                # Halaman kosong atau scan — catat sebagai issue
                result.issues.append(f"Halaman {page_num + 1} tidak mengandung teks (mungkin scan/gambar)")
                logger.warning(f"[CLEANING] Halaman {page_num + 1} kosong atau scan")

            pages.append(PageContent(
                page_number=page_num + 1,
                raw_text=raw_text,
            ))

        doc.close()
        return pages

    # ─────────────────────────────────────────────────────────────────
    # STEP 2: CLEANING PER HALAMAN
    # ─────────────────────────────────────────────────────────────────

    def _clean_page(self, page: PageContent) -> PageContent:
        """
        Pipeline cleaning untuk satu halaman:
        1. Normalisasi Unicode
        2. Fix PDF artifacts & ligature
        3. Hapus nomor halaman
        4. Normalisasi whitespace
        """
        text = page.raw_text

        # 1. Normalisasi Unicode (NFC)
        if settings.cleaning_fix_encoding:
            text = normalize_unicode(text)
            text = fix_common_pdf_artifacts(text)

        # 2. Hapus nomor halaman
        if settings.cleaning_remove_header_footer:
            text = remove_page_numbers(text)

        # 3. Normalisasi whitespace
        if settings.cleaning_normalize_whitespace:
            text = normalize_whitespace(text)

        # Update page object
        page.cleaned_text = text
        page.word_count = len(text.split())
        page.char_count = len(text)

        return page

    # ─────────────────────────────────────────────────────────────────
    # STEP 3: HAPUS HEADER/FOOTER LINTAS HALAMAN
    # ─────────────────────────────────────────────────────────────────

    def _remove_cross_page_artifacts(
        self, pages: list[PageContent]
    ) -> list[PageContent]:
        """
        Deteksi baris yang muncul berulang lintas halaman (header/footer)
        lalu hapus dari setiap halaman.
        """
        if not settings.cleaning_remove_header_footer:
            return pages

        # Kumpulkan semua baris dari semua halaman
        all_lines = []
        for page in pages:
            all_lines.extend(page.cleaned_text.split("\n"))

        # Hapus kandidat header/footer
        # (fungsi ini memfilter baris yang terlalu sering muncul)
        filtered_lines = remove_header_footer_candidates(
            all_lines, threshold=self._header_footer_threshold
        )

        # Bangun set baris yang dihapus
        removed = set(all_lines) - set(filtered_lines)
        removed_stripped = {l.strip() for l in removed if l.strip()}

        if removed_stripped:
            logger.info(f"[CLEANING] Header/footer dihapus: {removed_stripped}")

        # Update setiap halaman
        for page in pages:
            lines = page.cleaned_text.split("\n")
            clean_lines = [l for l in lines if l.strip() not in removed_stripped]
            page.cleaned_text = normalize_whitespace("\n".join(clean_lines))
            page.word_count = len(page.cleaned_text.split())
            page.char_count = len(page.cleaned_text)

        return pages

    # ─────────────────────────────────────────────────────────────────
    # STEP 4: GABUNG HALAMAN
    # ─────────────────────────────────────────────────────────────────

    def _merge_pages(self, pages: list[PageContent]) -> str:
        """
        Gabung semua halaman menjadi satu teks penuh.
        Gunakan double-newline sebagai pemisah halaman.
        """
        page_texts = [p.cleaned_text for p in pages if p.cleaned_text.strip()]
        merged = "\n\n".join(page_texts)
        return normalize_whitespace(merged)