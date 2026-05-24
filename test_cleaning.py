"""
test_cleaning.py
================
Script pengujian cepat untuk CleaningService rule-based.

Cara pakai:
  python test_cleaning.py <path_ke_file.pdf>

Atau tanpa argumen untuk menjalankan test dengan teks dummy:
  python test_cleaning.py
"""

import sys
import io
import json
import logging
from pathlib import Path

# Fix encoding Windows terminal
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Pastikan root project ada di path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from app.services.cleaning_service import CleaningService


def print_separator(title: str = "", char: str = "-", width: int = 70):
    if title:
        pad = max(0, width - len(title) - 2)
        print(f"\n{char * (pad // 2)} {title} {char * (pad - pad // 2)}")
    else:
        print(char * width)


def test_with_pdf(pdf_path: str):
    """Jalankan cleaning pada file PDF nyata dan cetak ringkasan hasilnya."""
    service = CleaningService()

    print_separator("MULAI CLEANING")
    print(f"File: {pdf_path}")

    result = service.clean_from_path(pdf_path)

    # ── Ringkasan Umum ─────────────────────────────────────────────
    print_separator("RINGKASAN UMUM")
    print(f"  Status          : {result.status.value.upper()}")
    print(f"  Total halaman   : {result.total_pages}")
    print(f"  Total kata      : {result.total_words:,}")
    print(f"  Total karakter  : {len(result.full_cleaned_text):,}")
    print(f"  Issues          : {len(result.issues)}")
    if result.issues:
        for issue in result.issues:
            print(f"    ⚠  {issue}")

    # ── Metadata UU ────────────────────────────────────────────────
    print_separator("METADATA DOKUMEN")
    if result.metadata:
        for k, v in result.metadata.items():
            print(f"  {k:12s}: {v}")
    else:
        print("  (tidak ditemukan metadata)")

    # ── Parsed Structure ───────────────────────────────────────────
    ps = result.parsed_structure
    print_separator("STRUKTUR HIERARKI")
    print(f"  Total BAB   : {ps.total_bab}")
    print(f"  Total Pasal : {ps.total_pasal}")
    print(f"  Total Ayat  : {ps.total_ayat}")

    if ps.bab_list:
        print("\n  Daftar BAB:")
        for bab in ps.bab_list:
            print(
                f"    BAB {bab.number:6s} | {bab.title[:40]:40s} | "
                f"Pasal {bab.pasal_start or '?'}–{bab.pasal_end or '?'} "
                f"({bab.pasal_count} pasal)"
            )

    if ps.pasal_list:
        print(f"\n  Sample 10 Pasal pertama:")
        for pasal in ps.pasal_list[:10]:
            print(
                f"    Pasal {pasal.number:6s} | BAB {pasal.bab_number or '?':6s} | "
                f"{pasal.ayat_count} ayat"
            )
        if len(ps.pasal_list) > 10:
            print(f"    ... dan {len(ps.pasal_list) - 10} pasal lainnya")

    # ── Preview Teks Bersih ────────────────────────────────────────
    print_separator("PREVIEW TEKS BERSIH (500 karakter pertama)")
    preview = result.full_cleaned_text[:500]
    print(preview)
    if len(result.full_cleaned_text) > 500:
        print("...")

    # ── Export JSON (opsional) ─────────────────────────────────────
    output_path = Path(pdf_path).with_suffix(".cleaned.json")
    summary = {
        "document_id"      : result.document_id,
        "source_filename"  : result.source_filename,
        "status"           : result.status.value,
        "total_pages"      : result.total_pages,
        "total_words"      : result.total_words,
        "total_chars"      : len(result.full_cleaned_text),
        "metadata"         : result.metadata,
        "parsed_structure" : {
            "total_bab"  : ps.total_bab,
            "total_pasal": ps.total_pasal,
            "total_ayat" : ps.total_ayat,
            "bab_list"   : [b.model_dump() for b in ps.bab_list],
            "pasal_list" : [p.model_dump() for p in ps.pasal_list],
        },
        "issues"           : result.issues,
        "full_cleaned_text": result.full_cleaned_text,
    }
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print_separator()
    print(f"✅ Output JSON disimpan ke: {output_path}")


def test_dummy():
    """Test sederhana dengan teks dummy tanpa PDF."""
    from app.services.cleaning_service import CleaningService
    from app.services.cleaning_service import _RE_PARSE_BAB, _RE_PARSE_PASAL

    sample_text = """
UNDANG-UNDANG REPUBLIK INDONESIA
NOMOR 11 TAHUN 2008
TENTANG INFORMASI DAN TRANSAKSI ELEKTRONIK

BAB I
KETENTUAN UMUM

Pasal 1

(1) Informasi Elektronik adalah satu atau sekumpulan data elektronik.
(2) Dokumen Elektronik adalah setiap Informasi Elektronik.

Pasal 2

Undang-Undang ini berlaku untuk setiap Orang yang melakukan perbuatan hukum.

BAB II
ASAS DAN TUJUAN

Pasal 3

(1) Pemanfaatan Teknologi Informasi dilaksanakan berdasarkan asas kepastian hukum.
(2) Pemanfaatan Teknologi Informasi dilaksanakan dengan tujuan untuk mencerdaskan.
"""

    service = CleaningService()

    print_separator("TEST PARS STRUKTUR (teks dummy)")

    ps = service._parse_structure(sample_text)
    print(f"BAB ditemukan   : {ps.total_bab}")
    print(f"Pasal ditemukan : {ps.total_pasal}")
    print(f"Ayat ditemukan  : {ps.total_ayat}")

    for bab in ps.bab_list:
        print(f"\n  {bab.full_header}")
        print(f"    Pasal {bab.pasal_start}–{bab.pasal_end} ({bab.pasal_count} pasal)")

    for pasal in ps.pasal_list:
        print(f"  {pasal.full_header} | BAB {pasal.bab_number} | {pasal.ayat_count} ayat")

    print_separator("TEST SELESAI")
    print("✅ Dummy test berhasil!")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        pdf_file = sys.argv[1]
        if not Path(pdf_file).exists():
            print(f"❌ File tidak ditemukan: {pdf_file}")
            sys.exit(1)
        test_with_pdf(pdf_file)
    else:
        print("Tidak ada argumen PDF. Menjalankan dummy test...\n")
        test_dummy()
