"""
ENDPOINT: /api/v1/cleaning
============================
REST API untuk CleaningService (rule-based, tanpa LLM).

Routes:
  POST /upload             → Upload PDF, jalankan cleaning, return ringkasan + stats
  POST /upload/preview     → Upload PDF, return teks bersih + struktur lengkap (untuk debug/test)
  POST /upload/structure   → Upload PDF, return HANYA parsed_structure (BAB, Pasal, Ayat)
"""

import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool

from app.services.cleaning_service import CleaningService
from app.models.schemas import ProcessingResponse, CleaningStats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cleaning", tags=["Cleaning"])

# Service diinstansiasi sekali (stateless, aman untuk shared)
_cleaning_service = CleaningService()

# Batas ukuran file PDF: 50 MB
_MAX_FILE_SIZE = 50 * 1024 * 1024


# ─────────────────────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _validate_pdf(file: UploadFile, pdf_bytes: bytes):
    """Validasi tipe dan ukuran file. Raise HTTPException jika tidak valid."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Hanya file PDF yang diterima (.pdf)",
        )
    if len(pdf_bytes) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File terlalu besar. Maksimal {_MAX_FILE_SIZE // (1024*1024)} MB.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 1: Ringkasan Cleaning
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/upload",
    response_model=ProcessingResponse,
    summary="Upload & bersihkan PDF — ringkasan",
    description="""
Upload file PDF undang-undang dan jalankan pipeline cleaning rule-based.

**Pipeline (5 tahap):**
1. Ekstraksi teks per halaman (PyMuPDF)
2. Cleaning per halaman — hapus noise, header/footer berulang, perbaiki OCR artifact
3. Gabung + normalisasi struktur UU (BAB, Pasal, Bagian, Ayat)
4. Ekstraksi metadata (jenis, nomor, tahun, tentang)
5. Pra-parsing struktur hierarki (deteksi BAB, Pasal, Ayat)

**Output:** Ringkasan statistik + metadata + preview teks 500 karakter.
""",
)
async def upload_and_clean(
    file: UploadFile = File(..., description="File PDF undang-undang"),
):
    pdf_bytes = await file.read()
    _validate_pdf(file, pdf_bytes)

    logger.info(f"[API/cleaning] Upload: {file.filename} ({len(pdf_bytes):,} bytes)")

    try:
        # CleaningService adalah sync — jalankan di thread pool agar tidak blocking event loop
        result = await run_in_threadpool(
            _cleaning_service.clean_from_bytes,
            pdf_bytes,
            file.filename,
        )
    except Exception as e:
        logger.error(f"[API/cleaning] Gagal: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Cleaning gagal: {str(e)}")

    ps = result.parsed_structure
    stats = CleaningStats(
        total_pages=result.total_pages,
        total_words=result.total_words,
        total_chars=len(result.full_cleaned_text),
        issues_found=len(result.issues),
    )

    return ProcessingResponse(
        success=True,
        message=f"Cleaning berhasil: {file.filename}",
        document_id=result.document_id,
        data={
            "status"              : result.status.value,
            "stats"               : stats.model_dump(),
            "metadata"            : result.metadata,
            "structure_summary"   : {
                "total_bab"  : ps.total_bab,
                "total_pasal": ps.total_pasal,
                "total_ayat" : ps.total_ayat,
            },
            "issues"              : result.issues,
            "cleaned_text_preview": result.full_cleaned_text[:500],
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 2: Full Preview (untuk debugging / inspeksi manual)
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/upload/preview",
    summary="Upload & bersihkan PDF — full preview (debug)",
    description="""
Sama dengan `/upload` tapi mengembalikan teks bersih **lengkap** dan
**struktur hierarki detail** (semua BAB dan Pasal yang terdeteksi).

Gunakan untuk inspeksi dan debugging kualitas hasil cleaning.

Parameter:
- `max_chars`: batas karakter teks bersih yang dikembalikan (default 10.000, 0 = semua)
""",
)
async def upload_and_preview(
    file: UploadFile = File(..., description="File PDF undang-undang"),
    max_chars: int = Query(
        default=10000,
        ge=0,
        description="Batas karakter teks bersih yang dikembalikan. 0 = kembalikan semua.",
    ),
):
    pdf_bytes = await file.read()
    _validate_pdf(file, pdf_bytes)

    try:
        result = await run_in_threadpool(
            _cleaning_service.clean_from_bytes,
            pdf_bytes,
            file.filename,
        )
    except Exception as e:
        logger.error(f"[API/cleaning/preview] Gagal: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    ps = result.parsed_structure

    cleaned_text = (
        result.full_cleaned_text
        if max_chars == 0
        else result.full_cleaned_text[:max_chars]
    )
    is_truncated = max_chars > 0 and len(result.full_cleaned_text) > max_chars

    return JSONResponse({
        "document_id"      : result.document_id,
        "source_filename"  : result.source_filename,
        "status"           : result.status.value,
        "total_pages"      : result.total_pages,
        "total_words"      : result.total_words,
        "total_chars"      : len(result.full_cleaned_text),
        "metadata"         : result.metadata,
        "structure"        : {
            "total_bab"  : ps.total_bab,
            "total_pasal": ps.total_pasal,
            "total_ayat" : ps.total_ayat,
            "bab_list"   : [b.model_dump() for b in ps.bab_list],
            "pasal_list" : [p.model_dump() for p in ps.pasal_list],
        },
        "issues"           : result.issues,
        "cleaned_text"     : cleaned_text,
        "truncated"        : is_truncated,
        "total_text_chars" : len(result.full_cleaned_text),
    })


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 3: Hanya Struktur Hierarki (untuk inspeksi cepat)
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/upload/structure",
    summary="Upload PDF — hanya parsed structure (BAB, Pasal, Ayat)",
    description="""
Upload PDF dan kembalikan **hanya hasil pra-parsing struktur hierarki** —
daftar lengkap semua BAB dan Pasal yang terdeteksi beserta posisi dan relasinya.

Berguna untuk:
- Verifikasi apakah struktur dokumen berhasil terdeteksi dengan benar
- Validasi sebelum proses chunking
""",
)
async def upload_and_get_structure(
    file: UploadFile = File(..., description="File PDF undang-undang"),
):
    pdf_bytes = await file.read()
    _validate_pdf(file, pdf_bytes)

    try:
        result = await run_in_threadpool(
            _cleaning_service.clean_from_bytes,
            pdf_bytes,
            file.filename,
        )
    except Exception as e:
        logger.error(f"[API/cleaning/structure] Gagal: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    ps = result.parsed_structure

    return JSONResponse({
        "document_id"    : result.document_id,
        "source_filename": result.source_filename,
        "status"         : result.status.value,
        "metadata"       : result.metadata,
        "structure"      : {
            "total_bab"  : ps.total_bab,
            "total_pasal": ps.total_pasal,
            "total_ayat" : ps.total_ayat,
            "bab_list"   : [
                {
                    "number"      : b.number,
                    "title"       : b.title,
                    "full_header" : b.full_header,
                    "pasal_start" : b.pasal_start,
                    "pasal_end"   : b.pasal_end,
                    "pasal_count" : b.pasal_count,
                }
                for b in ps.bab_list
            ],
            "pasal_list" : [
                {
                    "number"     : p.number,
                    "full_header": p.full_header,
                    "bab_number" : p.bab_number,
                    "ayat_count" : p.ayat_count,
                }
                for p in ps.pasal_list
            ],
        },
        "issues": result.issues,
    })