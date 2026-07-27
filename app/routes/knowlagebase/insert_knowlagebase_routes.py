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


class MultiFileResult(BaseModel):
    filename: str
    success: bool
    document_id: Optional[str] = None
    error: Optional[str] = None
    data: Optional[Dict] = None


class MultiUploadResponse(BaseModel):
    total_files: int
    success_count: int
    failed_count: int
    results: List[MultiFileResult]


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

    # Ambil cuplikan halaman pertama untuk preview before/after
    raw_snippet   = ""
    clean_snippet = ""
    if result.cleaned_pages:
        first_page = result.cleaned_pages[0]
        raw_snippet   = (first_page.raw_text or "")[:600]
        clean_snippet = (first_page.cleaned_text or "")[:600]

    return JSONResponse(content={
        "success": True,
        "message": f"Cleaning berhasil: {file.filename}",
        "document_id": result.document_id,
        "metadata": result.metadata,
        "repair_stats": result.repair_stats,
        "data": {
            "total_pages": result.total_pages,
            "total_words": result.total_words,
            "raw_snippet":   raw_snippet,
            "clean_snippet": clean_snippet,
        }
    })


@router.post("/upload-multi", summary="Upload & cleaning beberapa PDF sekaligus", response_model=MultiUploadResponse)
async def upload_and_clean_multi(
    files: List[UploadFile] = File(..., description="Satu atau lebih file PDF undang-undang"),
):
    """
    Upload dan cleaning beberapa file PDF secara berurutan.
    Setiap file diproses independently — jika satu gagal, file lain tetap diproses.
    """
    results: List[Dict] = []
    success_count = 0
    failed_count = 0

    for f in files:
        if not f.filename.lower().endswith(".pdf"):
            results.append(MultiFileResult(
                filename=f.filename,
                success=False,
                error="Hanya file PDF yang diterima (.pdf)",
            ).model_dump())
            failed_count += 1
            continue

        pdf_bytes = await f.read()
        try:
            result = await run_in_threadpool(
                get_cleaning_service().clean_from_bytes, pdf_bytes, f.filename
            )

            raw_snippet   = ""
            clean_snippet = ""
            if result.cleaned_pages:
                first_page    = result.cleaned_pages[0]
                raw_snippet   = (first_page.raw_text or "")[:600]
                clean_snippet = (first_page.cleaned_text or "")[:600]

            results.append(MultiFileResult(
                filename=f.filename,
                success=True,
                document_id=result.document_id,
                data={
                    "total_pages":    result.total_pages,
                    "total_words":    result.total_words,
                    "metadata":       result.metadata,
                    "repair_stats":   result.repair_stats,
                    "raw_snippet":    raw_snippet,
                    "clean_snippet":  clean_snippet,
                },
            ).model_dump())
            success_count += 1

        except Exception as e:
            results.append(MultiFileResult(
                filename=f.filename,
                success=False,
                error=f"Cleaning gagal: {str(e)}",
            ).model_dump())
            failed_count += 1

    return JSONResponse(content={
        "total_files":   len(files),
        "success_count": success_count,
        "failed_count":  failed_count,
        "results":       results,
    })


@router.post("/process-multi", summary="Cleaning → Chunking (+embed opsional) untuk beberapa PDF")
async def process_pdf_multi(
    files: List[UploadFile] = File(..., description="Satu atau lebih file PDF undang-undang"),
    embed: bool = Query(False),
    collection: Optional[str] = Query(None),
    include_raw_chunks: bool = Query(False, description="Sertakan seluruh raw chunks dalam response"),
):
    """
    Proses full pipeline (cleaning → chunking → embed opsional) untuk setiap PDF.
    File diproses berurutan; kegagalan satu file tidak menghentikan file berikutnya.
    """
    results: List[Dict] = []
    success_count = 0
    failed_count  = 0

    for f in files:
        if not f.filename.lower().endswith(".pdf"):
            results.append(MultiFileResult(
                filename=f.filename,
                success=False,
                error="Hanya file PDF yang diterima (.pdf)",
            ).model_dump())
            failed_count += 1
            continue

        pdf_bytes = await f.read()

        # Tentukan nama collection per file
        file_collection = collection or None

        try:
            cleaning_result = await run_in_threadpool(
                get_cleaning_service().clean_from_bytes, pdf_bytes, f.filename
            )
        except Exception as e:
            results.append(MultiFileResult(
                filename=f.filename,
                success=False,
                error=f"Cleaning gagal: {str(e)}",
            ).model_dump())
            failed_count += 1
            continue

        try:
            chunking_result = await get_chunking_service().chunk(cleaning_result)
        except Exception as e:
            results.append(MultiFileResult(
                filename=f.filename,
                success=False,
                error=f"Chunking gagal: {str(e)}",
            ).model_dump())
            failed_count += 1
            continue

        all_chunks = chunking_result.all_chunks
        raw_chunks = chunking_result.__dict__.get("raw_chunks", [])

        raw_snippet   = ""
        clean_snippet = ""
        if cleaning_result.cleaned_pages:
            fp            = cleaning_result.cleaned_pages[0]
            raw_snippet   = (fp.raw_text or "")[:600]
            clean_snippet = (fp.cleaned_text or "")[:600]

        file_data: Dict = {
            "cleaning_stats": {
                "total_pages":   cleaning_result.total_pages,
                "total_words":   cleaning_result.total_words,
                "metadata":      cleaning_result.metadata,
                "repair_stats":  cleaning_result.repair_stats,
                "raw_snippet":   raw_snippet,
                "clean_snippet": clean_snippet,
            },
            "chunking_stats": {
                "total_chunks": chunking_result.total_chunks,
                "level_0_count": len(chunking_result.level_0_chunks),
                "level_1_count": len(chunking_result.level_1_chunks),
                "level_2_count": len(chunking_result.level_2_chunks),
                "level_3_count": len(chunking_result.level_3_chunks),
                "parent_count": sum(1 for c in raw_chunks if c.get("type") == "parent"),
                "child_count":  sum(1 for c in raw_chunks if c.get("type") == "child"),
            },
            "embedding": None,
            "indexing":  None,
        }

        if include_raw_chunks:
            file_data["raw_chunks"] = raw_chunks

        if embed:
            try:
                embedded_chunks = await get_embedding_service().embed_chunks(all_chunks)
                try:
                    upsert_result = get_qdrant_service().upsert_chunks(
                        embedded_chunks, collection_name=file_collection
                    )
                    file_data["indexing"] = upsert_result
                except Exception as e:
                    file_data["indexing"] = {"error": str(e)}
                file_data["embedding"] = {
                    "model": settings.embedding_model,
                    "embedded_chunks": sum(1 for c in embedded_chunks if c.embedding is not None),
                }
            except Exception as e:
                file_data["embedding"] = {"error": str(e)}

        results.append(MultiFileResult(
            filename=f.filename,
            success=True,
            document_id=chunking_result.document_id,
            data=file_data,
        ).model_dump())
        success_count += 1

    return JSONResponse(content={
        "total_files":   len(files),
        "success_count": success_count,
        "failed_count":  failed_count,
        "results":       results,
    })


@router.post("/process", summary="Cleaning → Chunking (+ optional embed & index)")
async def process_pdf(
    file: UploadFile = File(..., description="File PDF undang-undang"),
    include_chunks_preview: bool = Query(False, description="Sertakan preview 20 chunk pertama"),
    include_raw_chunks: bool = Query(False, description="Sertakan seluruh raw parent-child chunks dalam response"),
    embed: bool = Query(False),
    collection: Optional[str] = Query(None),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Hanya file PDF yang diterima (.pdf)")

    pdf_bytes = await file.read()

    try:
        cleaning_result = await run_in_threadpool(
            get_cleaning_service().clean_from_bytes, pdf_bytes, file.filename
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleaning gagal: {str(e)}")

    try:
        chunking_result = await get_chunking_service().chunk(cleaning_result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chunking gagal: {str(e)}")

    all_chunks = chunking_result.all_chunks
    raw_chunks = chunking_result.__dict__.get("raw_chunks", [])

    # Cuplikan halaman pertama untuk preview before/after di dashboard
    raw_snippet   = ""
    clean_snippet = ""
    if cleaning_result.cleaned_pages:
        fp = cleaning_result.cleaned_pages[0]
        raw_snippet   = (fp.raw_text or "")[:600]
        clean_snippet = (fp.cleaned_text or "")[:600]

    response_data: Dict = {
        "cleaning_stats": {
            "total_pages": cleaning_result.total_pages,
            "total_words": cleaning_result.total_words,
            "metadata": cleaning_result.metadata,
            "repair_stats": cleaning_result.repair_stats,
            "raw_snippet":   raw_snippet,
            "clean_snippet": clean_snippet,
        },
        "chunking_stats": {
            "total_chunks": chunking_result.total_chunks,
            "level_0_count": len(chunking_result.level_0_chunks),
            "level_1_count": len(chunking_result.level_1_chunks),
            "level_2_count": len(chunking_result.level_2_chunks),
            "level_3_count": len(chunking_result.level_3_chunks),
            "parent_count": sum(1 for c in raw_chunks if c.get("type") == "parent"),
            "child_count": sum(1 for c in raw_chunks if c.get("type") == "child"),
        },
        "embedding": None,
        "indexing": None,
    }

    if embed:
        try:
            embedded_chunks = await get_embedding_service().embed_chunks(all_chunks)
            try:
                upsert_result = get_qdrant_service().upsert_chunks(embedded_chunks, collection_name=collection)
                response_data["indexing"] = upsert_result
            except Exception as e:
                response_data["indexing"] = {"error": str(e)}
            response_data["embedding"] = {
                "model": settings.embedding_model,
                "embedded_chunks": sum(1 for c in embedded_chunks if c.embedding is not None),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Embedding/indexing gagal: {str(e)}")

    if include_chunks_preview:
        response_data["chunks_preview"] = [
            {"chunk_id": c["chunk_id"], "type": c["type"], "section": c.get("section", ""), "text_preview": c["text"][:150]}
            for c in raw_chunks[:20]
        ]

    if include_raw_chunks:
        response_data["raw_chunks"] = raw_chunks

    return JSONResponse(content={
        "success": True,
        "message": f"Berhasil memproses: {chunking_result.total_chunks} chunks",
        "document_id": chunking_result.document_id,
        "data": response_data,
    })


@router.post("/process/chunks", summary="Kembalikan seluruh parent-child chunks dalam format JSON")
async def process_and_get_chunks(
    file: UploadFile = File(..., description="File PDF undang-undang"),
):
    """
    Upload PDF → cleaning → chunking → kembalikan array JSON parent-child chunks.
    Format output identik dengan contoh di app/document/uu_2_2002_full_parent_child_chunks.json.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Hanya file PDF yang diterima (.pdf)")

    pdf_bytes = await file.read()

    try:
        cleaning_result = await run_in_threadpool(
            get_cleaning_service().clean_from_bytes, pdf_bytes, file.filename
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleaning gagal: {str(e)}")

    try:
        chunking_result = await get_chunking_service().chunk(cleaning_result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chunking gagal: {str(e)}")

    raw_chunks = chunking_result.__dict__.get("raw_chunks", [])

    return JSONResponse(content=raw_chunks)

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
    try:
        names = await kb_service.list_collections()
        # kb_service.list_collections() sudah return nama yang bersih
        # tidak perlu filter _parent lagi
        return sorted(names)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gagal mengambil daftar KB: {str(e)}"
        )

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

@router.get("/preview/{base_name}", response_model=Dict)
async def get_kb_preview(base_name: str, limit: int = Query(10)):
    """Mendapatkan preview parent dan child chunks dari Knowledge Base."""
    try:
        formatted_name = base_name.lower().strip().replace(" ", "_")
        preview = await kb_service.get_chunks_preview(formatted_name, limit)
        return preview
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gagal mengambil preview KB: {str(e)}"
        )


@router.get("/monitor/{base_name}", response_model=Dict)
async def get_kb_monitor(base_name: str, preview_limit: int = Query(5)):
    """
    [Monitoring Tab] Satu endpoint untuk semua kebutuhan monitoring KB:
    - Nama collection parent & child
    - Jumlah point (parent_count, child_count)
    - Cuplikan dokumen dari kedua collection (parent_preview, child_preview)
    """
    try:
        formatted_name = base_name.lower().strip().replace(" ", "_")
        data = await kb_service.get_monitor_data(formatted_name, preview_limit)
        return data
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gagal mengambil data monitoring KB: {str(e)}"
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