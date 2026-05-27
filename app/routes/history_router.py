# history_router.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.postgres import get_db
from app.database.migration.models import RAGHistory

router = APIRouter()

# =========================================================
# GET ALL HISTORY
# =========================================================
@router.get("/")
def get_all_history(
    db: Session = Depends(get_db)
):
    histories = (
        db.query(RAGHistory)
        .order_by(RAGHistory.created_at.desc())
        .all()
    )

    results = []

    for item in histories :
        results.append({
            "id": item.id,
            "knowledge_base": item.knowledge_base,
            "provider": item.provider,
            "raw_transcribe": item.raw_transcribe,
            "repaired_text": item.repaired_text,
            "search_query": item.search_query,
            "retrieved_context": item.retrieved_context,
            "generate_material": item.generate_material,
            "compliance_score": item.compliance_score,
            "decision_status": item.decision_status,
            "created_at": item.created_at
        })

    return {
            "status": "success",
            "total": len(results),
            "data": results
        }
        

# =========================================================
# GET HISTORY DETAIL
# =========================================================
@router.get("/{history_id}")
def get_history_detail(
    history_id: int,
    db: Session = Depends(get_db)
):
    
    history = (
        db.query(RAGHistory)
        .filter(RAGHistory.id == history_id)
        .first()
    )

    if not history :
        raise HTTPException(
            status_code=404, 
            detail="History tidak ditemukan"
        )
    
    return {
        "status": "success",
        "data": {
            "id": history.id,
            "knowledge_base": history.knowledge_base,
            "provider": history.provider,
            "raw_transcribe": history.raw_transcribe,
            "repaired_text": history.repaired_text,
            "search_query": history.search_query,
            "retrieved_context": history.retrieved_context,
            "generate_material": history.generate_material,
            "compliance_score": history.compliance_score,
            "decision_status": history.decision_status,
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
        db.query(RAGHistory)
        .filter(RAGHistory.id == history_id)
        .first()
    )

    if not history : 
        raise HTTPException(
            status_code=404, 
            detail="History tidak ditemukan"
        )
    
    db.delete(history)
    db.commit()

    return {
        "status": "success",
        "message": f"History dengan id {history_id} berhasil dihapus"
    }