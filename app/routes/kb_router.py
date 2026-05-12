from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.postgres import get_db
from app.core.qdrant import qdrant_db
from app.database.migration.uud import UUDArticle
from app.services.ingestion_service import run_ingestion_upload

router = APIRouter()

ALLOWED_CONTENT_TYPES = ["application/pdf"]
MAX_FILE_SIZE = 20 
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE * 1024 * 1024

# UPLOAD PDF

@router.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    collection_name: str = Form(default="uud_articles"),
    db: Session = Depends(get_db)
):
    """
    Upload dan proses file PDF ke knowledge base.
    File akan di-parse, di-chunk per Pasal, lalu disimpan ke PostgreSQL + Qdrant.
    """

    #Validasi tipe file
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Hanya file PDF yang diperbolehkan. File Anda: {file.content_type}"
        )
    
    #Baca konten file 
    file_contents = await file.read()

    #Validasi ukuran file
    if len(file_contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code = 400,
            detail=f"Ukuran file terlalu besar! Maksimal {MAX_FILE_SIZE} MB. File Anda: {len(file_contents) / (1024 * 1024):.2f} MB"
        )
    
    if len(file_contents) == 0:
        raise HTTPException(
            status_code=400,
            detail="File kosong!"
        )
    
    try:
        result = run_ingestion_upload(
            file_contents=file_contents,
            db=db,
            collection_name=collection_name
        )
        return {
            "status": "success",
            "filename": file.filename,
            "collection": collection_name,
            "total_segments": result.get("total_segments", 0),
            "message": f"Berhasil mengindeks {result.get('total_segments', 0)} segmen dari file {file.filename}"

        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Terjadi kesalahan saat memproses file: {str(e)}"
        )
    

# List Dokumen

@router.get("/documents")
def list_documents(
    collection_name: str = "uud_articles",
    db: Session = Depends(get_db)
):
    """
    Ambil daftar semua dokumen (per Pasal) yang tersimpan di database.
    """

    try:
        articles = db.query(UUDArticle).order_by(UUDArticle.id).all()

        #Kelompokkan berdasarkan BAB
        grouped = {}
        for article in articles:
            bab = article.bab or "Tidak Diketahui"

            if bab not in grouped:
                grouped[bab] = []

            grouped[bab].append({
                "id": article.id,
                "bab": article.bab,
                "pasal": article.pasal,
                "preview": article.isi_teks[:120] + "..." if len(article.isi_teks) > 120 else article.isi_teks
            })
        return {
            "status": "success",
            "collection": collection_name,
            "total": len(articles),
            "grouped": grouped
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Terjadi kesalahan saat mengambil dokumen: {str(e)}"
        )
    
# LIST COLLECTIONS

@router.get("/collections")
def list_collections():
    """
    Ambil daftar semua collection yang tersedia di Qdrant.
    """

    try:
        collections = qdrant_db.client.get_collections()
        names = [c.name for c in collections.collections]
        return {
            "status": "success",
            "collections": names
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Terjadi kesalahan saat mengambil daftar collection: {str(e)}"
        )
    
#STATS COLLECTION   

@router.get("/stats") 
def collection_stats(
    collection_name: str = "uud_articles",
    db: Session = Depends(get_db)
):
    """
    Statistik jumlah dokumen di PostgreSQL dan jumlah vector di Qdrant.
    """
    try:
        total_db = db.query(UUDArticle).count()

        try:
            info = qdrant_db.client.get_collection(collection_name)
            total_vectors = info.points_count
        except Exception as e:
            total_vectors = 0

        return {
            "status": "success",
            "collection": collection_name,
            "total_db": total_db,
            "total_vectors": total_vectors
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Terjadi kesalahan saat mengambil statistik collection: {str(e)}"
        )

#DELETE SATU PASAL

@router.delete("/documents/{article_id}")
def delete_document(
    article_id: int,
    collection_name: str = "uud_articles",
    db: Session = Depends(get_db)
):
    """
    Hapus satu entri Pasal dari POstgresSQL dan Qdrant berdasarkan ID.
    """

    article = db.query(UUDArticle).filter(UUDArticle.id == article_id).first()
    if not article :
        raise HTTPException(
            status_code=404,
            detail=f"Dokumen dengan ID {article_id} tidak ditemukan"
        )
    
    try:
        #Hapus dari Qdrant
        qdrant_db.client.delete(
            collection_name=collection_name,
            points_selector=[article_id]
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Terjadi kesalahan saat menghapus dari Qdrant: {str(e)}"
        )
    
    #Hapus dari PostgreSQL
    db.delete(article)
    db.commit()

    return {
        "status": "success",
        "message": f"Dokumen dengan ID {article.pasal} berhasil dihapus"
    }

# DELETE SEMUA (RESET COLLECTION)

@router.delete("/reset")
def reset_collection(
    collection_name: str = "uud_articles",
    db: Session = Depends(get_db)
):  

    """
    Hapus SEMUA dokumen dari PostgreSQL dan reset collection di Qdrant.
    Gunakan dengan hati-hati!
    """

    try:
        #Hapus semua dari PostgreSQL
        deleted_count = db.query(UUDArticle).delete()
        db.commit()

        # Recreate collection di Qdrant (otomatis menghapus semua vector)
        qdrant_db.client.recreate_collection(
            collection_name=collection_name,
            vectors_config={"size":384, "distance": "Cosine"}
        )

        return {
            "status": "success",
            "message": f"Berhasil menghapus {deleted_count} dokumen dan mereset collection '{collection_name}'"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Terjadi kesalahan saat mereset collection: {str(e)}"
        )
    



