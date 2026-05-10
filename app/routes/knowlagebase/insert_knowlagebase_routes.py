import asyncio
from qdrant_client.http import models
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.services.knowledgebase.kb_service import kb_service
from typing import List, Dict
from pydantic import BaseModel


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