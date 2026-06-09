# history_router.py (moved to app/routes/evaluasi)
import logging, json, datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.models import (
    RAGHistory,
    RAGProcess,
    RAGSession,
    RAGASEvaluation
)

from app.core.postgres import get_db
from app.database.models import RAGHistory

router = APIRouter()
logger = logging.getLogger(__name__)


def _parse_json_field(raw: str | None) -> dict | list | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _serialize_evaluation(item: RAGASEvaluation) -> dict:
    return {
        "id": item.id,
        "evaluation_type": item.evaluation_type,
        "question": item.question,
        "answer": item.answer,
        "ground_truth": item.ground_truth,
        "faithfulness": item.faithfulness,
        "answer_relevancy": item.answer_relevancy,
        "context_precision": item.context_precision,
        "context_recall": item.context_recall,

        "risk_faithfulness": item.risk_faithfulness,
        "coverage_pct": item.coverage_pct,
        "evaluated_segments": (
            json.loads(item.evaluated_segments)
            if item.evaluated_segments
            else []
        ),

        "overall_score": item.overall_score,

        "status": item.status,
        "created_at": item.created_at,
    }


def _serialize_process(item: RAGProcess) -> dict:
    session = item.session
    evaluations = sorted(
        list(item.evaluations or []),
        key=lambda ev: ev.created_at or datetime.min,
        reverse=True,
    )
    latest_eval = evaluations[0] if evaluations else None

    latest_metrics = _serialize_evaluation(latest_eval) if latest_eval else None
    ragas_metrics = None
    ragas_status = "skipped"
    if latest_eval:
        ragas_status = latest_eval.status or "error"
        ragas_metrics = {
            "faithfulness": latest_eval.faithfulness,
            "answer_relevancy": latest_eval.answer_relevancy,
            "context_precision": latest_eval.context_precision,
            "context_recall": latest_eval.context_recall,

            "risk_faithfulness": latest_eval.risk_faithfulness,
            "coverage_pct": latest_eval.coverage_pct,
            "evaluated_segments": (
                json.loads(latest_eval.evaluated_segments)
                if latest_eval.evaluated_segments
                else []
            ),

            "overall_score": latest_eval.overall_score,
}

    return {
        "id": item.id,
        "session_id": item.session_id,
        "session_title": session.session_title if session else None,
        "knowledge_base": session.knowledge_base if session else None,
        "provider": session.provider if session else None,
        "raw_transcribe": item.raw_transcribe,
        "repaired_text": item.repaired_text,
        "search_query": item.search_query,
        "retrieved_context": item.retrieved_context,
        "generate_material": _parse_json_field(item.generated_material),
        "compliance_score": item.compliance_score,
        "decision_status": item.decision_status,
        "ragas_metrics": ragas_metrics,
        "ragas_status": ragas_status,
        "ragas_evaluation": latest_metrics,
        "ragas_evaluations": [_serialize_evaluation(ev) for ev in evaluations],
        "created_at": item.created_at,
    }

# ── GET ALL ───────────────────────────────────────────────────────────────────

@router.get("/")
def get_all_history(db: Session = Depends(get_db)):
    histories = (
        db.query(RAGProcess)
        .order_by(RAGProcess.created_at.desc())
        .all()
    )
    results = [_serialize_process(h) for h in histories]
    return {
            "status": "success",
            "total": len(results),
            "data": results
        }
        


# =========================================================
# GET HISTORY DETAIL
# =========================================================
@router.get("/{history_id}")
def get_history_detail(history_id: int, db: Session = Depends(get_db)):
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
            "raw_transcribe": history.raw_transcribe,
            "repaired_text": history.repaired_text,
            "search_query": history.search_query,
            "retrieved_context": history.retrieved_context,
            "generated_material": history.generated_material,
            "compliance_score": history.compliance_score,
            "decision_status": history.decision_status,
            "created_at": history.created_at
        }
    }

# =========================================================
# DELETE HISTORY
# =========================================================
@router.delete("/{history_id}")
def delete_history(history_id: int, db: Session = Depends(get_db)):
    """
    Endpoint untuk menghapus satu riwayat berdasarkan ID.
    Memiliki logika Cascade Clean-up: Jika sesi dari riwayat tersebut sudah kosong,
    maka data Sesi (`RAGSession`) tersebut juga akan otomatis dihapus dari database.
    """
    history = (
        db.query(RAGHistory)
        .filter(RAGHistory.id == history_id)
        .first()
    )
    if not history:
        raise HTTPException(status_code=404, detail="History tidak ditemukan")

    session_id = history.session_id
    db.delete(history)
    db.commit()

    remaining = db.query(RAGProcess).filter(RAGProcess.session_id == session_id).count()
    if remaining == 0:
        session = db.query(RAGSession).filter(RAGSession.id == session_id).first()
        if session:
            db.delete(session)
            db.commit()

    return {
        "status": "success",
        "message": f"History dengan id {history_id} berhasil dihapus",
    }

# ── UPDATE TITLE ────────────────────────────────────────────────────────────────

@router.put("/{history_id}/title")
def update_history_title(
    history_id: int,
    request: UpdateHistoryTitleRequest,
    db: Session = Depends(get_db),
):
    success = RAGHistoryService.update_title(
        db=db,
        history_id=history_id,
        session_title=request.session_title,
    )

    if not success:
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
