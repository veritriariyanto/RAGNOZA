# app/services/history/history_service.py

import logging

from sqlalchemy.orm import Session

from app.database.models.rag_process import RAGProcess
from app.database.models.ragas_evaluation import RAGASEvaluation

logger = logging.getLogger(__name__)


class HistoryService:

    @staticmethod
    def update_ragas(
        db: Session,
        history_id: int,
        ragas_result: dict,
    ) -> bool:
        """
        Memasukkan satu baris evaluasi metrik baru ke dalam tabel RAGASEvaluation.
        Fungsi ini dipanggil oleh background task sesaat setelah mesin evaluator (:8001) selesai berhitung.
        """
        try:
            process = db.query(RAGProcess).filter(RAGProcess.id == history_id).first()
            if not process:
                logger.warning("[RAGHistory] update_ragas: process_id=%d tidak ditemukan", history_id)
                return False

            metrics = ragas_result.get("metrics") or {}
            input_payload = ragas_result.get("input") or {}

            evaluation_type = input_payload.get("source_label") or (
                "manual_with_ground_truth" if input_payload.get("ground_truth") else "auto_evaluation"
            )

            evaluation = RAGASEvaluation(
                process_id=process.id,
                evaluation_type=evaluation_type,
                question=input_payload.get("question"),
                answer=input_payload.get("answer"),
                ground_truth=input_payload.get("ground_truth"),

                faithfulness=metrics.get("faithfulness"),
                answer_relevancy=metrics.get("answer_relevancy"),
                context_precision=metrics.get("context_precision"),
                context_recall=metrics.get("context_recall"),

                risk_faithfulness=metrics.get("risk_faithfulness"),

                # FIX #7 (Prioritas 4)
                faithfulness_summary=metrics.get("faithfulness_summary"),
                faithfulness_qa=metrics.get("faithfulness_qa"),

                answer_qa=input_payload.get("answer_qa"),

                # FIX : audit trail — teks persis yang dinilai LLM judge
                faithfulness_text=input_payload.get("faithfulness_text"),
                answer_risk_text=input_payload.get("answer_risk"),

                evaluated_segments=metrics.get(
                    "answer_faithfulness_segment", []
                ),
                status=ragas_result.get("status", "error"),
            )

            db.add(evaluation)
            db.commit()

            logger.info(
                "[RAGHistory] RAGAS updated — process_id=%d | evaluation_id=%d | status=%s",
                history_id,
                evaluation.id,
                evaluation.status,
            )
            return True

        except Exception as exc:
            db.rollback()
            logger.error("[RAGHistory] Gagal update RAGAS: %s", exc, exc_info=True)
            return False
        
    