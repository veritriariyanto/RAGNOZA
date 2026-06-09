# app/routes/evaluasi/history_router.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.postgres import get_db
# Import model baru yang sudah sukses dimigrasi
from app.database.migration.history import LegalMaterialHistory

router = APIRouter()

# =========================================================
# GET ALL HISTORY (Untuk kebutuhan Tabel / List di Frontend)
# =========================================================
@router.get("/")
def get_all_history(
    db: Session = Depends(get_db)
):
    histories = (
        db.query(LegalMaterialHistory)
        .order_by(LegalMaterialHistory.created_at.desc())
        .all()
    )

    results = []

    for item in histories:
        # Defensif ekstrak data dari kolom JSONB Postgres
        material_dict = item.generated_material if isinstance(item.generated_material, dict) else {}
        meta_dict = item.rag_metadata if isinstance(item.rag_metadata, dict) else {}

        results.append({
            "id": item.id,
            "title": item.title,  # Tambahan judul untuk UI list yang lebih informatif
            "status": item.status,
            "knowledge_base": item.knowledge_base,
            "provider": item.provider,
            "raw_transcribe": item.transcription_raw,
            "repaired_text": item.transcription_repaired,
            "search_query": meta_dict.get("query_used"),
            "retrieved_context_preview": meta_dict.get("retrieved_context_preview"),
            "generate_material": item.generated_material, # Mengembalikan full JSON object ke frontend
            # Mengambil score & status langsung dari payload JSONB LLM
            "compliance_score": material_dict.get("compliance_score"),
            "decision_status": material_dict.get("decision_status"),
            "created_at": item.created_at
        })

    return {
        "status": "success",
        "total": len(results),
        "data": results
    }


# =========================================================
# GET HISTORY DETAIL (Untuk Halaman Detail / View Analisis)
# =========================================================
@router.get("/{history_id}")
def get_history_detail(
    history_id: int,
    db: Session = Depends(get_db)
):
    history = (
        db.query(LegalMaterialHistory)
        .filter(LegalMaterialHistory.id == history_id)
        .first()
    )

    if not history:
        raise HTTPException(
            status_code=404, 
            detail="History tidak ditemukan"
        )
    
    material_dict = history.generated_material if isinstance(history.generated_material, dict) else {}
    meta_dict = history.rag_metadata if isinstance(history.rag_metadata, dict) else {}
    
    return {
        "status": "success",
        "data": {
            "id": history.id,
            "title": history.title,
            "status": history.status,
            "knowledge_base": history.knowledge_base,
            "provider": history.provider,
            "raw_transcribe": history.transcription_raw,
            "repaired_text": history.transcription_repaired,
            "search_query": meta_dict.get("query_used"),
            "retrieved_context_preview": meta_dict.get("retrieved_context_preview"),
            "generate_material": history.generated_material,
            "compliance_score": material_dict.get("compliance_score"),
            "decision_status": material_dict.get("decision_status"),
            "evaluation": history.evaluation, # Log status evaluasi RAGAS di background
            "created_at": history.created_at
        }
    }


# =========================================================
# DELETE HISTORY
# =========================================================
@router.delete("/{history_id}")
def delete_history(
    history_id: int,
    db: Session = Depends(get_db)
):
    history = (
        db.query(LegalMaterialHistory)
        .filter(LegalMaterialHistory.id == history_id)
        .first()
    )

    if not history: 
        raise HTTPException(
            status_code=404, 
            detail="History tidak ditemukan"
        )
    
    try:
        db.delete(history)
        db.commit()
        return {
            "status": "success",
            "message": f"History dengan id {history_id} berhasil dihapus"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Gagal menghapus data dari database: {str(e)}"
        )