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
    try:
        formatted_name = base_name.lower().strip().replace(" ", "_")
        parent_col = f"{formatted_name}_parent"
        
        from qdrant_client.http import models
        scroll_filter = models.Filter(
            must=[
                models.FieldCondition(key="section_type", match=models.MatchValue(value="pembukaan"))
            ]
        )
        
        # ✅ AsyncQdrantClient.scroll() mengembalikan TUPLE (points, next_offset)
        # WAJIB: pakai `await` + unpack tuple
        points, next_offset = await kb_service.db.scroll(
            collection_name=parent_col,
            limit=1,
            with_payload=True,
            with_vectors=False,
            scroll_filter=scroll_filter
        )
        
        if not points:
            raise HTTPException(
                status_code=404, 
                detail=f"Knowledge base '{base_name}' tidak ditemukan."
            )
        
        # Akses payload dari point pertama
        payload = points[0].payload
        
        return {
            "name": formatted_name,
            "document_id": payload.get("document_id"),
            "uu_number": payload.get("uu_number"),
            "tahun": payload.get("tahun"),
            "judul_uu": payload.get("judul_uu"),
            "created_at": payload.get("created_at")
        }
        
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

@router.post("/search/{base_name}")
async def search_kb(
    base_name: str,
    query: str = Form(...),
    section_type: str = Form(None),
    pasal_type: str = Form(None),
    limit: int = Form(5)
):
    try:
        formatted_name = base_name.lower().strip().replace(" ", "_")
        child_col = f"{formatted_name}_child"
        parent_col = f"{formatted_name}_parent"
        
        # Build filter
        filter_conditions = []
        
        if section_type:
            filter_conditions.append(
                models.FieldCondition(key="section_type", match=models.MatchValue(value=section_type))
            )
        if pasal_type:
            filter_conditions.append(
                models.FieldCondition(key="pasal_type", match=models.MatchValue(value=pasal_type))
            )
        
        query_filter = models.Filter(must=filter_conditions) if filter_conditions else None
        
        # ✅ 1. Embedding dipindah ke thread terpisah (CPU-bound)
        query_vector = await asyncio.to_thread(kb_service.embeddings.embed_query, query)
        
        # ✅ 2. Tambahkan `await` untuk AsyncQdrantClient
        search_response = await kb_service.db.query_points(
            collection_name=child_col,
            query=query_vector,
            limit=limit,
            query_filter=query_filter,
            with_payload=True
        )
        
        results = []
        for hit in search_response.points:
            parent_id = hit.payload.get("parent_id")
            
            # ✅ 3. `retrieve` juga harus di-`await`
            parent = await kb_service.db.retrieve(
                collection_name=parent_col,
                ids=[parent_id],
                with_payload=True,
                with_vectors=False
            )
            
            parent_data = parent[0].payload if parent else {}
            
            results.append({
                "score": hit.score,
                "child": {
                    "content": hit.payload.get("content"),
                    "raw_text": hit.payload.get("raw_text"),
                    "type": hit.payload.get("type"),
                    "reference_label": hit.payload.get("reference_label"),
                    "keyword_tags": hit.payload.get("keyword_tags", [])
                },
                "parent": {
                    "content": parent_data.get("content"),
                    "reference_label": parent_data.get("reference_label"),
                    "pasal_nomor": parent_data.get("pasal_nomor")
                }
            })
            
        return {
            "query": query,
            "total_results": len(results),
            "results": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal melakukan pencarian: {str(e)}")