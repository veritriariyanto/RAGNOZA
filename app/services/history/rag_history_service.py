# app/services/history/rag_history_service.py

import json
import logging

from sqlalchemy.orm import Session

from app.database.models.rag_process import RAGProcess
from app.database.models.rag_session import RAGSession
from app.database.models.ragas_evaluation import RAGASEvaluation

logger = logging.getLogger(__name__)


class RAGHistoryService:

    @staticmethod
    def _get_or_create_session(
        db: Session,
        session_id: int | None,
        session_title: str | None,
        knowledge_base: str,
        provider: str,
    ) -> RAGSession | None:
        if session_id is not None:
            existing_session = db.query(RAGSession).filter(RAGSession.id == session_id).first()
            if existing_session:
                return existing_session

        session = RAGSession(
            session_title=session_title,
            knowledge_base=knowledge_base,
            provider=provider,
        )
        db.add(session)
        db.flush()
        return session

    @staticmethod
    def save_history(
        db: Session,
        session_title: str | None,
        knowledge_base: str,
        provider: str,
        raw_transcribe: str,
        repaired_text: str,
        search_query: str,
        retrieved_context: str,
        final_material,
        session_id: int | None = None,
    ) -> RAGProcess | None:
        try:
            session = RAGHistoryService._get_or_create_session(
                db=db,
                session_id=session_id,
                session_title=session_title,
                knowledge_base=knowledge_base,
                provider=provider,
            )

            if session is None:
                raise RuntimeError("Gagal membuat atau memuat rag_session")

            process = RAGProcess(
                session_id=session.id,
                raw_transcribe=raw_transcribe,
                repaired_text=repaired_text,
                search_query=search_query,
                retrieved_context=retrieved_context,
                generated_material=(
                    json.dumps(final_material.model_dump(), ensure_ascii=False)
                    if final_material else None
                ),
                compliance_score=(
                    final_material.compliance_score if final_material else None
                ),
                decision_status=(
                    final_material.decision_status if final_material else None
                ),
            )

            db.add(process)
            db.commit()
            db.refresh(process)

            logger.info(
                "[RAGHistory] Tersimpan — session_id=%d | process_id=%d | kb=%s | score=%s | status=%s",
                session.id,
                process.id,
                knowledge_base,
                process.compliance_score,
                process.decision_status,
            )
            return process

        except Exception as exc:
            db.rollback()
            logger.error("[RAGHistory] Gagal simpan: %s", exc, exc_info=True)
            return None

    @staticmethod
    def update_ragas(
        db: Session,
        history_id: int,
        ragas_result: dict,
    ) -> bool:
        """
        Simpan satu baris evaluasi baru pada ragas_evaluation untuk satu proses.
        Dipanggil setelah evaluasi RAGAS selesai (background task).
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
                coverage_pct=metrics.get("coverage_pct"),

                answer_qa=input_payload.get("answer_qa"),

                evaluated_segments=metrics.get(
                    "evaluated_segments", []
                ),

                overall_score=metrics.get("overall_score"),
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
        
    @staticmethod
    def update_title(
        db: Session,
        history_id: int,
        session_title: str,
    ) -> bool:
        try:
            process = (
                db.query(RAGProcess)
                .filter(RAGProcess.id == history_id)
                .first()
            )

            if not process:
                logger.warning(
                    "[RAGHistory] update_title: process_id=%d tidak ditemukan",
                    history_id
                )
                return False

            session = db.query(RAGSession).filter(RAGSession.id == process.session_id).first()
            if not session:
                logger.warning(
                    "[RAGHistory] update_title: session untuk process_id=%d tidak ditemukan",
                    history_id,
                )
                return False

            session.session_title = session_title.strip()

            db.commit()

            logger.info(
                "[RAGHistory] Title updated — session_id=%d | title=%s",
                session.id,
                session_title,
            )

            return True

        except Exception as exc:
            db.rollback()
            logger.error(
                "[RAGHistory] Gagal update title: %s",
                exc,
                exc_info=True
            )
            return False
        
    @staticmethod
    def get_ragas_metrics(
        db: Session,
        history_id: int,
    ) -> dict | None:
        """
        Ambil metrics dari baris RAGASEvaluation terbaru untuk process_id=history_id.
        Return dict { "metrics": {...} } atau None jika belum ada.
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
                "coverage_pct": evaluation.coverage_pct,

                "evaluated_segments": evaluation.evaluated_segments or [],
            
                "overall_score": evaluation.overall_score,
    }
}

    @staticmethod
    def get_by_id(
        db: Session,
        history_id: int,
    ):
        """
        Gabungkan RAGProcess + RAGASEvaluation terbaru menjadi satu objek
        yang dibutuhkan router reeval (question, context, answer, answer_qa).
        """
        from types import SimpleNamespace

        process = db.query(RAGProcess).filter(RAGProcess.id == history_id).first()
        if not process:
            return None

        evaluation = (
            db.query(RAGASEvaluation)
            .filter(RAGASEvaluation.process_id == history_id)
            .order_by(RAGASEvaluation.id.desc())
            .first()
        )

        return SimpleNamespace(
            question=evaluation.question,
            context=process.retrieved_context,
            answer=evaluation.answer,
            answer_qa=evaluation.answer_qa,
        )