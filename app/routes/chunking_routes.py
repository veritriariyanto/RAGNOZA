"""
Endpoint routes migrated from app/api/v1/endpoints/chunking.py
"""

import logging
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Body, Query
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool

from app.services.cleaning_service import CleaningService
from app.services.chunking_service import ChunkingService
from app.services.embedding_service import EmbeddingService
from app.services.qdrant_service import QdrantService
from app.models.schemas import (ProcessingResponse, ChunkingStats, CleaningResult, CleaningStatus)
from app.utils.text_utils import count_tokens
from app.config import settings

router = APIRouter(prefix="/api/v1/chunking", tags=["Chunking"])

logger = logging.getLogger(__name__)

# Singleton services
_cleaning_service = CleaningService()
_chunking_service = ChunkingService()
_embedding_service = EmbeddingService()
_qdrant_service = QdrantService()

_MAX_FILE_SIZE = 50 * 1024 * 1024


@router.post("/process", response_model=ProcessingResponse, summary="Upload PDF → Cleaning → Chunking → (opsional) Embed & Index ke Qdrant")
async def process_pdf(
    file: UploadFile = File(..., description="File PDF undang-undang"),
    include_chunks_preview: bool = Query(False, description="Sertakan preview chunks di response"),
    embed: bool = Query(False, description="Embed chunks dan index ke Qdrant setelah chunking"),
    collection: Optional[str] = Query(None, description="Override nama collection (jika None, menggunakan dual-collection default)"),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Hanya file PDF yang diterima (.pdf)")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Ukuran file terlalu besar. Maksimal 50MB.")

    logger.info(f"[API/chunking/process] Memproses file: {file.filename} (embed={embed})")

    try:
        cleaning_result = await run_in_threadpool(_cleaning_service.clean_from_bytes, pdf_bytes, file.filename)
    except Exception as e:
        logger.error(f"[API/chunking/process] Cleaning gagal: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Cleaning gagal: {str(e)}")

    try:
        chunking_result = await _chunking_service.chunk(cleaning_result)
    except Exception as e:
        logger.error(f"[API/chunking/process] Chunking gagal: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chunking gagal: {str(e)}")

    all_chunks = chunking_result.all_chunks
    total_tokens = sum(c.metadata.token_count for c in all_chunks)
    avg_tokens = total_tokens / len(all_chunks) if all_chunks else 0

    stats = ChunkingStats(
        total_chunks=chunking_result.total_chunks,
        level_0_count=len(chunking_result.level_0_chunks),
        level_1_count=len(chunking_result.level_1_chunks),
        level_2_count=len(chunking_result.level_2_chunks),
        level_3_count=len(chunking_result.level_3_chunks),
        avg_tokens_per_chunk=round(avg_tokens, 1),
    )

    response_data = {"cleaning_stats": {"total_pages": cleaning_result.total_pages, "total_words": cleaning_result.total_words, "issues": cleaning_result.issues}, "chunking_stats": stats.model_dump(), "metadata": chunking_result.metadata, "embedding": None, "indexing": None}

    if embed:
        try:
            embedded_chunks = await _embedding_service.embed_chunks(all_chunks)
            emb_count = sum(1 for c in embedded_chunks if c.embedding is not None)
            emb_dim = len(embedded_chunks[0].embedding) if embedded_chunks and embedded_chunks[0].embedding else 0

            response_data["embedding"] = {"model": settings.embedding_model, "embedded_chunks": emb_count, "vector_dim": emb_dim}
            logger.info(f"[API/chunking/process] Embedding selesai: {emb_count} chunks, dim={emb_dim}")

            try:
                upsert_result = _qdrant_service.upsert_chunks(embedded_chunks, collection_name=collection)
                response_data["indexing"] = upsert_result
            except Exception as e:
                logger.warning(f"[API/chunking/process] Qdrant upsert gagal: {e}")
                response_data["indexing"] = {"error": str(e)}

        except Exception as e:
            logger.error(f"[API/chunking/process] Embedding/indexing gagal: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Embedding/indexing gagal: {str(e)}")

    if include_chunks_preview:
        response_data["chunks_preview"] = [
            {"chunk_id": c.chunk_id, "level": c.metadata.hierarchy_level.value, "level_number": c.metadata.level_number, "token_count": c.metadata.token_count, "has_embedding": c.embedding is not None, "parent_chunk_id": c.metadata.parent_chunk_id, "is_parent": c.metadata.is_parent, "preview": c.preview, "bab": c.metadata.bab_title, "pasal": c.metadata.pasal_title, "ayat": c.metadata.ayat_number} for c in all_chunks[:20]
        ]

    return ProcessingResponse(success=True, message=f"Berhasil memproses: {chunking_result.total_chunks} chunks dari {file.filename}", document_id=chunking_result.document_id, data=response_data)
