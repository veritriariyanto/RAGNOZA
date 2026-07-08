#app/services/history/process_query_service.py

import logging
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.database.models.rag_process import RAGProcess
from app.database.models.ragas_evaluation import RAGASEvaluation

logger = logging.getLogger(__name__)

class ProcessQueryService:

    @staticmethod
    def get_ragas_metrics(
        db: Session,
        history_id: int,
    ) -> dict | None:
        """
        Ambil metrik RAGAS terbaru untuk satu process ID.
        Return None jika belum ada evaluasi.
        """
        evaluation = (
            db.query(RAGASEvaluation)
            .filter(RAGASEvaluation.process_id == history_id)
            .order_by(RAGASEvaluation.id.desc())
            .first()
        )
        if not evaluation:
            return None

        return {
            "metrics": {
                "faithfulness": evaluation.faithfulness,
                "answer_relevancy": evaluation.answer_relevancy,
                "context_precision": evaluation.context_precision,
                "context_recall": evaluation.context_recall,

                "risk_faithfulness": evaluation.risk_faithfulness,

                "evaluated_segments": evaluation.evaluated_segments or [],

                # FIX #7 (Prioritas 4)
                "faithfulness_summary": evaluation.faithfulness_summary,
                "faithfulness_qa": evaluation.faithfulness_qa,
                }
            }

    @staticmethod
    def get_by_id(
        db: Session,
        history_id: int,
    ):
        """
        Gabungkan data RAGProcess + RAGASEvaluation terbaru menjadi satu objek.
        Dipakai oleh router re-evaluasi untuk mengambil teks lama.
        Return None jika process atau evaluation tidak ditemukan.
        """

        process = db.query(RAGProcess).filter(RAGProcess.id == history_id).first()
        if not process:
            logger.warning(
                "[ProcessQueryService] get_by_id: process_id=%d tidak ditemukan", history_id
            )
            return None

        evaluation = (
            db.query(RAGASEvaluation)
            .filter(RAGASEvaluation.process_id == history_id)
            .order_by(RAGASEvaluation.id.desc())
            .first()
        )
        if not evaluation:
            logger.warning(
                "[ProcessQueryService] get_by_id: evaluation_id=%d tidak ditemukan", history_id
            )
            return None

        return SimpleNamespace(
            question=evaluation.question,
            context=process.retrieved_context,
            answer=evaluation.answer,
            answer_qa=evaluation.answer_qa,
        )