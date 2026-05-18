"""
ENDPOINT: /api/v1/chunking
===========================
REST API untuk Hierarchical (Parent-Child) Chunking + Embedding Service.

Routes:
- POST /process           → Upload PDF → Cleaning → Chunking → (opsional) Embed & Index
- POST /from-text         → Chunking dari teks langsung (untuk testing)
- POST /search            → Similarity search berdasarkan teks query
- GET  /collections       → Daftar collection di Qdrant
"""

import logging
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Body, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

from app.services.cleaning_service import CleaningService
from app.services.chunking_service import ChunkingService
from app.services.embedding_service import EmbeddingService
from app.services.qdrant_service import QdrantService
from app.models.schemas import (
    ProcessingResponse,
    ChunkingStats,
    CleaningResult,
    CleaningStatus,
)
from app.utils.text_utils import count_tokens
from app.config import settings

router = APIRouter(prefix="/chunking", tags=["Chunking"])

# Singleton services (model dimuat satu kali)
_cleaning_service = CleaningService()
_chunking_service = ChunkingService()
_embedding_service = EmbeddingService()
_qdrant_service = QdrantService()


# ──────────────────────────────────────────────────────────────────
# POST /process
# ──────────────────────────────────────────────────────────────────

@router.post(
    "/process",
    response_model=ProcessingResponse,
    summary="Upload PDF → Cleaning → Chunking → (opsional) Embed & Index ke Qdrant",
    description="""
Pipeline lengkap: Upload PDF → Cleaning → Parent-Child Chunking → (opsional) Embedding & Indexing.

**Parent-Child Chunking Levels:**

| Level | Tipe   | Deskripsi                                  | Role   |
|-------|--------|--------------------------------------------|--------|
| 0     | Document | Intro/header dokumen                     | Parent |
| 1     | BAB    | Konten penuh satu BAB + semua Pasal+Ayat   | Parent |
| 2     | Pasal  | Konten penuh Pasal + semua Ayat (jika ada) | Parent/Child |
| 3     | Ayat   | Satu Ayat (unit retrieval kecil)           | Child  |

**RAG Flow:**
1. Vector search → temukan Ayat child yang relevan
2. Fetch `parent_chunk_id` → load Pasal parent sebagai konteks penuh
3. LLM menerima konteks lengkap

Aktifkan `embed=true` untuk langsung embed dan index ke Qdrant.
""",
)
async def process_pdf(
    file: UploadFile = File(..., description="File PDF undang-undang"),
    include_chunks_preview: bool = Query(False, description="Sertakan preview chunks di response"),
    embed: bool = Query(False, description="Embed chunks dan index ke Qdrant setelah chunking"),
    collection: Optional[str] = Query(None, description="Nama collection Qdrant (default dari settings)"),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Hanya file PDF yang diterima (.pdf)")

    MAX_SIZE = 50 * 1024 * 1024
    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="Ukuran file terlalu besar. Maksimal 50MB.")

    logger.info(f"[API] Process: {file.filename} (embed={embed})")

    # Step 1: Cleaning
    try:
        cleaning_result = await _cleaning_service.clean_from_bytes(
            pdf_bytes=pdf_bytes,
            source_filename=file.filename,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleaning gagal: {str(e)}")

    # Step 2: Chunking (Parent-Child)
    try:
        chunking_result = await _chunking_service.chunk(cleaning_result)
    except Exception as e:
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

    response_data = {
        "cleaning_stats": {
            "total_pages": cleaning_result.total_pages,
            "total_words": cleaning_result.total_words,
            "issues": cleaning_result.issues,
        },
        "chunking_stats": stats.model_dump(),
        "metadata": chunking_result.metadata,
        "embedding": None,
        "indexing": None,
    }

    # Step 3 (opsional): Embedding + Indexing ke Qdrant
    if embed:
        try:
            embedded_chunks = await _embedding_service.embed_chunks(all_chunks)
            emb_count = sum(1 for c in embedded_chunks if c.embedding is not None)
            emb_dim = len(embedded_chunks[0].embedding) if embedded_chunks and embedded_chunks[0].embedding else 0

            response_data["embedding"] = {
                "model": settings.embedding_model,
                "embedded_chunks": emb_count,
                "vector_dim": emb_dim,
            }
            logger.info(f"[API] Embedding selesai: {emb_count} chunks, dim={emb_dim}")

            # Step 4: Upsert ke Qdrant
            try:
                col = collection or settings.embedding_collection
                upsert_result = _qdrant_service.upsert_chunks(
                    embedded_chunks, collection_name=col
                )
                response_data["indexing"] = upsert_result
                logger.info(f"[API] Qdrant upsert: {upsert_result}")
            except Exception as e:
                logger.warning(f"[API] Qdrant upsert gagal (embedding tetap OK): {e}")
                response_data["indexing"] = {"error": str(e)}

        except Exception as e:
            logger.error(f"[API] Embedding gagal: {e}")
            raise HTTPException(status_code=500, detail=f"Embedding gagal: {str(e)}")

    # Preview opsional
    if include_chunks_preview:
        response_data["chunks_preview"] = [
            {
                "chunk_id": c.chunk_id,
                "level": c.metadata.hierarchy_level.value,
                "level_number": c.metadata.level_number,
                "token_count": c.metadata.token_count,
                "has_embedding": c.embedding is not None,
                "parent_chunk_id": c.metadata.parent_chunk_id,
                "preview": c.preview,
                "bab": c.metadata.bab_title,
                "pasal": c.metadata.pasal_title,
                "ayat": c.metadata.ayat_number,
            }
            for c in all_chunks[:20]
        ]

    return ProcessingResponse(
        success=True,
        message=f"Berhasil: {chunking_result.total_chunks} chunks dari {file.filename}"
                + (f" | {response_data['embedding']['embedded_chunks']} embedded" if embed and response_data["embedding"] else ""),
        document_id=chunking_result.document_id,
        data=response_data,
    )


# ──────────────────────────────────────────────────────────────────
# POST /from-text
# ──────────────────────────────────────────────────────────────────

@router.post(
    "/from-text",
    summary="Chunking dari teks langsung (testing)",
    description="Jalankan parent-child chunking langsung dari teks UU (bypass PDF cleaning).",
)
async def chunk_from_text(
    text: str = Body(..., embed=True, description="Teks UU yang sudah bersih"),
    filename: str = Body(default="manual_input.txt", embed=True),
    embed: bool = Body(default=False, embed=True, description="Embed hasil chunks"),
):
    if not text.strip():
        raise HTTPException(status_code=400, detail="Teks tidak boleh kosong")

    token_count = count_tokens(text)
    logger.info(f"[API] Chunk from text: {token_count} tokens")

    cleaning_result = CleaningResult(
        source_filename=filename,
        total_pages=1,
        full_cleaned_text=text,
        status=CleaningStatus.SUCCESS,
    )

    try:
        chunking_result = await _chunking_service.chunk(cleaning_result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chunking gagal: {str(e)}")

    all_chunks = chunking_result.all_chunks

    # Opsional embed
    if embed:
        try:
            all_chunks = await _embedding_service.embed_chunks(all_chunks)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Embedding gagal: {str(e)}")

    return JSONResponse({
        "document_id": chunking_result.document_id,
        "total_chunks": chunking_result.total_chunks,
        "breakdown": {
            "level_0_document": len(chunking_result.level_0_chunks),
            "level_1_bab": len(chunking_result.level_1_chunks),
            "level_2_pasal": len(chunking_result.level_2_chunks),
            "level_3_ayat": len(chunking_result.level_3_chunks),
        },
        "chunks": [
            {
                "chunk_id": c.chunk_id,
                "level": c.metadata.hierarchy_level.value,
                "level_number": c.metadata.level_number,
                "bab": c.metadata.bab_title,
                "pasal": c.metadata.pasal_title,
                "ayat": c.metadata.ayat_number,
                "tokens": c.metadata.token_count,
                "parent_chunk_id": c.metadata.parent_chunk_id,
                "has_embedding": c.embedding is not None,
                "content": c.content,
            }
            for c in all_chunks
        ],
    })


# ──────────────────────────────────────────────────────────────────
# POST /search
# ──────────────────────────────────────────────────────────────────

@router.post(
    "/search",
    summary="Similarity Search berdasarkan teks query",
    description="""
Embed query teks menggunakan model yang sama, lalu cari chunks paling relevan di Qdrant.

**Parent-Child RAG Flow:**
1. Child chunks ditemukan (Ayat / Pasal leaf)
2. Response menyertakan `parent_chunk_id` → client bisa fetch konteks penuh
""",
)
async def search_chunks(
    query: str = Body(..., embed=True, description="Pertanyaan atau teks yang dicari"),
    top_k: int = Body(default=5, embed=True, description="Jumlah hasil (max 20)"),
    score_threshold: float = Body(default=0.3, embed=True, description="Minimum similarity score"),
    filter_level: Optional[int] = Body(default=None, embed=True, description="Filter level (3=Ayat, 2=Pasal, None=semua)"),
    collection: Optional[str] = Body(default=None, embed=True, description="Nama collection Qdrant"),
    fetch_parent: bool = Body(default=False, embed=True, description="Sertakan parent chunk di setiap hasil"),
):
    if not query.strip():
        raise HTTPException(status_code=400, detail="Query tidak boleh kosong")

    top_k = min(top_k, 20)
    col = collection or settings.embedding_collection

    # Embed query
    try:
        query_vector = _embedding_service.embed_text(query.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding query gagal: {str(e)}")

    # Search Qdrant
    try:
        results = _qdrant_service.search(
            query_vector=query_vector,
            top_k=top_k,
            collection_name=col,
            score_threshold=score_threshold,
            filter_level=filter_level,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search gagal: {str(e)}")

    # Opsional: fetch parent untuk setiap hasil
    if fetch_parent and results:
        for hit in results:
            parent_id = hit.get("parent_chunk_id")
            if parent_id:
                parent = _qdrant_service.get_chunk_by_id(parent_id, col)
                hit["parent_context"] = parent.get("content") if parent else None
            else:
                hit["parent_context"] = None

    return JSONResponse({
        "query": query,
        "collection": col,
        "model": settings.embedding_model,
        "total_results": len(results),
        "results": results,
    })


# ──────────────────────────────────────────────────────────────────
# GET /collections
# ──────────────────────────────────────────────────────────────────

@router.get(
    "/collections",
    summary="Daftar collection Qdrant",
)
async def list_collections():
    health = _qdrant_service.health_check()
    return JSONResponse(health)