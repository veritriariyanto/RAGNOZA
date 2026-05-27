# app/routes/knowlagebase/insert_knowlagebase_routes.py

import asyncio
from qdrant_client.http import models
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from app.services.knowlagebase.kb_service import kb_service
from typing import List, Dict, Optional
from pydantic import BaseModel
from app.core.config import settings

# Lazy singletons: create services only when first needed to avoid heavy imports at module import
_cleaning_service = None
_chunking_service = None
_embedding_service = None
_qdrant_service = None


def get_cleaning_service():
    global _cleaning_service
    if _cleaning_service is None:
        from app.services.knowlagebase.cleaning_service import CleaningService

        _cleaning_service = CleaningService()
    return _cleaning_service


def get_chunking_service():
    global _chunking_service
    if _chunking_service is None:
        from app.services.knowlagebase.chunking_service import ChunkingService

        _chunking_service = ChunkingService()
    return _chunking_service


def get_embedding_service():
    global _embedding_service
    if _embedding_service is None:
        from app.services.knowlagebase.embedding_service import EmbeddingService

        _embedding_service = EmbeddingService()
    return _embedding_service


def get_qdrant_service():
    global _qdrant_service
    if _qdrant_service is None:
        from app.services.knowlagebase.qdrant_service import QdrantService

        _qdrant_service = QdrantService()
    return _qdrant_service


router = APIRouter()


# Response Models
class IngestResponse(BaseModel):
    status: str
    document_id: str
    total_pasal: int
    metadata: Dict
    message: str


class CollectionStats(BaseModel):
    name: str
    parent_count: int
    child_count: int
    status: str


class DeleteResponse(BaseModel):
    status: str
    message: str
    deleted_collections: List[str]


# ---------- Cleaning & Chunking endpoints added here ----------
# Note: services are created lazily via getters (get_cleaning_service(), etc.)


@router.post("/upload", summary="Upload & cleaning (alias for cleaning route)")
async def upload_and_clean(file: UploadFile = File(..., description="File PDF undang-undang")):
    pdf_bytes = await file.read()
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Hanya file PDF yang diterima (.pdf)")

    try:
        result = await run_in_threadpool(get_cleaning_service().clean_from_bytes, pdf_bytes, file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleaning gagal: {str(e)}")

    return JSONResponse(content={
        "success": True,
        "message": f"Cleaning berhasil: {file.filename}",
        "document_id": result.document_id,
        "data": {
            "total_pages": result.total_pages,
            "total_words": result.total_words,
        }
    })


@router.post("/process", summary="Chunking (+ optional embed & index)")
async def process_pdf(
    file: UploadFile = File(..., description="File PDF undang-undang"),
    include_chunks_preview: bool = Query(False),
    embed: bool = Query(False),
    collection: Optional[str] = Query(None),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Hanya file PDF yang diterima (.pdf)")

    pdf_bytes = await file.read()

    try:
        cleaning_result = await run_in_threadpool(get_cleaning_service().clean_from_bytes, pdf_bytes, file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleaning gagal: {str(e)}")

    try:
        chunking_result = await get_chunking_service().chunk(cleaning_result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chunking gagal: {str(e)}")

    all_chunks = chunking_result.all_chunks

    response_data = {"cleaning_stats": {"total_pages": cleaning_result.total_pages}, "chunking_stats": {"total_chunks": chunking_result.total_chunks}, "embedding": None, "indexing": None}

    if embed:
        try:
            embedded_chunks = await get_embedding_service().embed_chunks(all_chunks)
            try:
                upsert_result = get_qdrant_service().upsert_chunks(embedded_chunks, collection_name=collection)
                response_data["indexing"] = upsert_result
            except Exception as e:
                response_data["indexing"] = {"error": str(e)}
            response_data["embedding"] = {"model": settings.embedding_model, "embedded_chunks": sum(1 for c in embedded_chunks if c.embedding is not None)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Embedding/indexing gagal: {str(e)}")

    if include_chunks_preview:
        response_data["chunks_preview"] = [{"chunk_id": c.chunk_id, "preview": c.preview} for c in all_chunks[:20]]

    return JSONResponse(content={"success": True, "message": f"Berhasil memproses: {chunking_result.total_chunks} chunks", "document_id": chunking_result.document_id, "data": response_data})

# ---------- end additions ----------


@router.post("/ingest", response_model=IngestResponse)
async def ingest_kb(
    base_name: str = Form(...), 
    file: UploadFile = File(...)
):
    """
    Endpoint untuk membuat KB baru dari file PDF.
    Akan menghasilkan koleksi {base_name}_parent dan {base_name}_child di Qdrant.
    
    Args:
        base_name: Nama knowledge base (akan dinormalisasi)
        file: File PDF undang-undang
    
    Returns:
        IngestResponse dengan detail dokumen yang di-ingest
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=400, 
            detail="Hanya file PDF yang diperbolehkan."
        )

    try:
        content = await file.read()
        # Normalisasi nama koleksi
        formatted_name = base_name.lower().strip().replace(" ", "_")
        
        result = await kb_service.create_knowledgebase(
            base_name=formatted_name, 
            file_content=content
        )
        
        return IngestResponse(
            status=result["status"],
            document_id=result["document_id"],
            total_pasal=result["total_pasal"],
            metadata=result["metadata"],
            message=f"Knowledge base '{formatted_name}' berhasil dibuat dengan {result['total_pasal']} pasal."
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Gagal memproses dokumen: {str(e)}"
        )


@router.get("/list", response_model=List[str])
async def list_kb():
    """
    Mendapatkan daftar semua Knowledge Base yang tersedia.
    
    Returns:
        List nama knowledge base (tanpa suffix _parent/_child)
    """
    try:
        names = await kb_service.list_collections()
        return sorted(names)
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Gagal mengambil daftar KB: {str(e)}"
        )


@router.get("/stats/{base_name}", response_model=CollectionStats)
async def get_kb_stats(base_name: str):
    """
    Mendapatkan statistik dari sebuah Knowledge Base.
    
    Args:
        base_name: Nama knowledge base
    
    Returns:
        Statistik jumlah parent dan child documents
    """
    try:
        formatted_name = base_name.lower().strip().replace(" ", "_")
        stats = await kb_service.get_collection_stats(formatted_name)
        
        if stats.get("status") == "error":
            raise HTTPException(
                status_code=404, 
                detail=f"Knowledge base '{base_name}' tidak ditemukan."
            )
        
        return CollectionStats(
            name=formatted_name,
            parent_count=stats["parent_count"],
            child_count=stats["child_count"],
            status=stats["status"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Gagal mengambil statistik: {str(e)}"
        )


@router.get("/info/{base_name}", response_model=Dict)
async def get_kb_info(base_name: str):
    """
    Mendapatkan informasi detail dari sebuah Knowledge Base.
    """
    try:
        # ✅ Route hanya delegasi ke service
        info = await kb_service.get_kb_info(base_name)
        return info
        
    except ValueError as e:
        # Handle "not found" dari service
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Gagal mengambil informasi KB: {str(e)}"
        )
    
@router.delete("/delete/{base_name}", response_model=DeleteResponse)
async def delete_kb(base_name: str):
    """
    Menghapus Knowledge Base (Parent & Child) dari Qdrant.
    
    Args:
        base_name: Nama knowledge base yang akan dihapus
    
    Returns:
        Konfirmasi penghapusan
    """
    try:
        formatted_name = base_name.lower().strip().replace(" ", "_")
        
        # Cek apakah koleksi ada
        existing_collections = await kb_service.list_collections()
        if formatted_name not in existing_collections:
            raise HTTPException(
                status_code=404, 
                detail=f"Knowledge base '{base_name}' tidak ditemukan."
            )

        # Hapus KB
        await kb_service.delete_knowledgebase(formatted_name)
        
        return DeleteResponse(
            status="success",
            message=f"Knowledge base '{formatted_name}' berhasil dihapus.",
            deleted_collections=[
                f"{formatted_name}_parent",
                f"{formatted_name}_child"
            ]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Gagal menghapus KB: {str(e)}"
        )


@router.get("/collections")
async def list_qdrant_collections():
    """Dapatkan statistik/metadata collections dari Qdrant (detailed)."""
    try:
        qdrant = get_qdrant_service()
        detailed = qdrant.get_collections_detailed()
        return JSONResponse(content=detailed)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal mengambil collections dari Qdrant: {str(e)}")