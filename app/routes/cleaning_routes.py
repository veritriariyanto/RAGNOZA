"""
Endpoint routes migrated from app/api/v1/endpoints/cleaning.py
"""

import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool

from app.services.cleaning_service import CleaningService
from app.database.models.schemas import ProcessingResponse, CleaningStats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cleaning", tags=["Cleaning"])

# Service singleton
_cleaning_service = CleaningService()

# Batas ukuran file PDF: 50 MB
_MAX_FILE_SIZE = 50 * 1024 * 1024


def _validate_pdf(file: UploadFile, pdf_bytes: bytes):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Hanya file PDF yang diterima (.pdf)")
    if len(pdf_bytes) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File terlalu besar. Maksimal {_MAX_FILE_SIZE // (1024*1024)} MB.")


@router.post("/upload", response_model=ProcessingResponse, summary="Upload & bersihkan PDF — ringkasan")
async def upload_and_clean(file: UploadFile = File(..., description="File PDF undang-undang")):
    pdf_bytes = await file.read()
    _validate_pdf(file, pdf_bytes)

    logger.info(f"[API/cleaning] Upload: {file.filename} ({len(pdf_bytes):,} bytes)")

    try:
        result = await run_in_threadpool(_cleaning_service.clean_from_bytes, pdf_bytes, file.filename)
    except Exception as e:
        logger.error(f"[API/cleaning] Gagal: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Cleaning gagal: {str(e)}")

    ps = result.parsed_structure
    stats = CleaningStats(total_pages=result.total_pages, total_words=result.total_words, total_chars=len(result.full_cleaned_text), issues_found=len(result.issues))

    return ProcessingResponse(
        success=True,
        message=f"Cleaning berhasil: {file.filename}",
        document_id=result.document_id,
        data={
            "status": result.status.value,
            "stats": stats.model_dump(),
            "metadata": result.metadata,
            "structure_summary": {
                "total_bab": ps.total_bab,
                "total_pasal": ps.total_pasal,
                "total_ayat": ps.total_ayat,
            },
            "issues": result.issues,
            "cleaned_text_preview": result.full_cleaned_text[:500],
        },
    )
