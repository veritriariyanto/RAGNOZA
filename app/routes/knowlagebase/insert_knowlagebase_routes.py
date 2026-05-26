#insert_knowlagebase_routes.py

import asyncio
from fileinput import filename
from qdrant_client.http import models
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.services.knowledgebase.kb_service import kb_service
from typing import List, Dict, Any, Annotated
from pydantic import BaseModel
import hashlib


router = APIRouter()


# Response Models
class FileIngestResult(BaseModel):
    filename: str
    kb_name: str
    document_id: str
    total_pasal: int
    metadata: Dict[str, Any]
    file_hash: str
    status: str

class FailedFileResult(BaseModel):
    filename: str
    reason: str

class MultipleIngestResponse(BaseModel):
    status: str
    total_uploaded: int
    total_success: int
    total_failed: int
    results: List[FileIngestResult]
    failed_files: List[FailedFileResult]


class CollectionStats(BaseModel):
    name: str
    parent_count: int
    child_count: int
    status: str


class DeleteResponse(BaseModel):
    status: str
    message: str
    deleted_collections: List[str]


@router.post(
    "/ingest-multiple",
    response_model=MultipleIngestResponse,
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["files", "base_name"],
                        "properties": {
                            "files": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "format": "binary"  # ← kunci utama!
                                },
                                "description": "Upload satu atau banyak PDF files"
                            },
                            "base_name": {
                                "type": "string",
                                "description": "Nama knowledge base (akan dinormalisasi)"
                            }
                        }
                    }
                }
            },
            "required": True
        }
    }
)
async def ingest_kb(
    files: List[UploadFile] = File(...),       # ← kembali ke cara lama
    base_name: str = Form(...)
):

    """
    Upload multiple PDF sekaligus untuk knowledge base.
    Akan menghasilkan koleksi {base_name}_parent dan {base_name}_child di Qdrant.
    
    Args:
        base_name: Nama knowledge base (akan dinormalisasi)
        files: Daftar file PDF undang-undang
    
    Returns:
        IngestResponse dengan detail dokumen yang di-ingest
    """
    if not files:
        raise HTTPException(
            status_code=400, 
            detail="Tidak ada File yang diupload."
        )
    
    results = []
    failed_files = []

    try:
        # normalisasi nama base collection
        formatted_base_name = (
            base_name.lower().strip().replace(" ", "_")
        )
        for file in files:

            try :

                #validasi extension
                if not file.filename.lower().endswith(".pdf"):
                    failed_files.append({
                        "filename": file.filename,
                        "reason": "File bukan PDF"
                    })
                    continue

                #baca conten file
                content = await file.read()

                #validasi file kosong
                if not content:
                    failed_files.append({
                        "filename": file.filename,
                        "reason": "File kosong"
                    })
                    continue

                #hash file untuk deteksi duplikat
                file_hash = hashlib.md5(content).hexdigest()

                #nama kb unik per file
                file_name_clean = (
                    file.filename.replace(".pdf", "").replace(" ", "_").lower()
                )

                kb_name = f"{formatted_base_name}_{file_name_clean}"

                # ingest ke qdrant 
                result = await kb_service.create_knowledgebase(
                    base_name=kb_name,
                    file_content=content
                )

                results.append({
                    "filename": file.filename,
                    "kb_name": kb_name,
                    "document_id": result["document_id"],
                    "total_pasal": result["total_pasal"],
                    "metadata": result["metadata"],
                    "file_hash": file_hash,
                    "status": "success"
                })

            except Exception as file_error:
                failed_files.append({
                    "filename": file.filename,
                    "reason": str(file_error)
                })

        return {
            "status": "success",
            "total_uploaded": len(files),
            "total_success": len(results),
            "total_failed": len(failed_files),
            "results": results,
            "failed_files": failed_files
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gagal memproses knowledge base: {str(e)}"
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