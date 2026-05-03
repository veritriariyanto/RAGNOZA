from fastapi import APIRouter, HTTPException

from app.core.qdrant import qdrant_db

router = APIRouter()


@router.get("/collections")
async def list_collections():
    """Melihat daftar knowledge base yang sudah di-ingest"""
    collections = qdrant_db.get_all_collections()
    return {"available_collections": collections}


@router.post("/collections/create")
async def create_collection(collection_name: str, vector_size: int = 384):
    """Membuat koleksi baru di Qdrant"""
    try:
        qdrant_db.init_collection(collection_name=collection_name, vector_size=vector_size)
        return {"status": "success", "message": f"Koleksi '{collection_name}' berhasil dibuat."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal membuat koleksi: {str(e)}")


@router.delete("/collections/{collection_name}")
async def delete_collection(collection_name: str):
    """Menghapus koleksi dari Qdrant"""
    try:
        qdrant_db.client.delete_collection(collection_name=collection_name)
        return {"status": "success", "message": f"Koleksi '{collection_name}' berhasil dihapus."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal menghapus koleksi: {str(e)}")