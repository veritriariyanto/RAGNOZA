"""
ENDPOINT: /api/v1/cleaning
============================
Menyediakan REST API untuk Cleaning Service.

Routes:
- POST /upload        → Upload PDF dan jalankan cleaning
- GET  /status/{id}   → Cek status cleaning (future: async)
"""

import logging

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

from app.services.cleaning_service import CleaningService
from app.models.schemas import ProcessingResponse, CleaningStats

router = APIRouter(prefix="/cleaning", tags=["Cleaning"])
_cleaning_service = CleaningService()


@router.post(
    "/upload",
    response_model=ProcessingResponse,
    summary="Upload dan bersihkan dokumen PDF",
    description="""
Upload file PDF undang-undang dan jalankan proses cleaning.

**Pipeline cleaning yang dijalankan:**
1. Ekstraksi teks per halaman (PyMuPDF)
2. Perbaikan encoding & unicode artifacts
3. Penghapusan header/footer berulang
4. Normalisasi whitespace
5. Ekstraksi metadata UU (nomor, tahun, tentang)

**Output:** Teks bersih beserta metadata dokumen, siap untuk proses chunking.
""",
)
async def upload_and_clean(
    file: UploadFile = File(..., description="File PDF undang-undang"),
):
    # Validasi tipe file
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Hanya file PDF yang diterima (.pdf)",
        )

    # Batas ukuran file: 50MB
    MAX_SIZE = 50 * 1024 * 1024
    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Ukuran file terlalu besar. Maksimal 50MB.",
        )

    logger.info(f"[API] Upload file: {file.filename} ({len(pdf_bytes):,} bytes)")

    try:
        result = await _cleaning_service.clean_from_bytes(
            pdf_bytes=pdf_bytes,
            source_filename=file.filename,
        )
    except Exception as e:
        logger.error(f"[API] Cleaning gagal: {e}")
        raise HTTPException(status_code=500, detail=f"Cleaning gagal: {str(e)}")

    stats = CleaningStats(
        total_pages=result.total_pages,
        total_words=result.total_words,
        total_chars=len(result.full_cleaned_text),
        issues_found=len(result.issues),
    )

    return ProcessingResponse(
        success=True,
        message=f"Cleaning berhasil untuk {file.filename}",
        document_id=result.document_id,
        data={
            "stats": stats.model_dump(),
            "metadata": result.metadata,
            "issues": result.issues,
            "status": result.status.value,
            # Preview teks bersih (500 karakter pertama)
            "cleaned_text_preview": result.full_cleaned_text[:500],
        },
    )


@router.post(
    "/upload-and-preview",
    summary="Upload, bersihkan, dan tampilkan teks bersih lengkap",
    description="Sama dengan /upload tapi mengembalikan full cleaned text (untuk debugging).",
)
async def upload_and_preview(
    file: UploadFile = File(...),
    max_chars: int = 5000,
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Hanya file PDF yang diterima")

    pdf_bytes = await file.read()

    try:
        result = await _cleaning_service.clean_from_bytes(
            pdf_bytes=pdf_bytes,
            source_filename=file.filename,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return JSONResponse({
        "document_id": result.document_id,
        "source_filename": result.source_filename,
        "total_pages": result.total_pages,
        "total_words": result.total_words,
        "metadata": result.metadata,
        "issues": result.issues,
        "cleaned_text": result.full_cleaned_text[:max_chars],
        "truncated": len(result.full_cleaned_text) > max_chars,
    })