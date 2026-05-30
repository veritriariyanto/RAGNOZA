"""
evaluator/app/services/evaluation_service.py

Orchestrator evaluasi RAGAS di evaluator microservice.
Memformat hasil RAGAS menjadi response yang konsisten dan siap dikembalikan ke service utama.
"""

import logging
from typing import Optional

from app.schemas import EvaluationMetrics, EvaluationResponse
from app.services.ragas_service import ragas_service

logger = logging.getLogger(__name__)


class EvaluationService:
    async def run_evaluation(
        self,
        question: str,
        context: str,
        answer: str,
        ground_truth: Optional[str] = None,
        source_label: str = "rag_pipeline",
    ) -> EvaluationResponse:
        """
        Jalankan evaluasi RAGAS dan kembalikan EvaluationResponse yang terstruktur.

        Args:
            question     : Pertanyaan asli user
            context      : Context yang di-retrieve dari Qdrant
            answer       : Jawaban final LLM
            ground_truth : Opsional — proxy atau ground truth sebenarnya
            source_label : Label untuk logging

        Returns:
            EvaluationResponse dengan metrics atau error
        """
        input_payload = {
            "question": question,
            "context": context[:200] + "..." if len(context) > 200 else context,
            "answer": answer[:200] + "..." if len(answer) > 200 else answer,
            "ground_truth": ground_truth,
        }

        if not ragas_service.is_available:
            logger.warning("[EvalService:%s] RAGAS tidak tersedia", source_label)
            return EvaluationResponse(
                status="error",
                error="RAGAS service tidak tersedia",
                input=input_payload,
            )

        try:
            logger.info(
                "[EvalService:%s] Memulai evaluasi | q=%d chars | ctx=%d chars | ans=%d chars",
                source_label,
                len(question),
                len(context),
                len(answer),
            )

            result = await ragas_service.evaluate_rag(
                question=question,
                context=context,
                answer=answer,
                ground_truth=ground_truth,
            )

            scores = result.to_pandas().to_dict(orient="records")[0]

            def _safe_round(val) -> Optional[float]:
                return round(float(val), 4) if val is not None else None

            faithfulness_score    = _safe_round(scores.get("faithfulness"))
            answer_relevancy_score = _safe_round(scores.get("answer_relevancy"))
            context_precision_score = _safe_round(scores.get("context_precision"))
            context_recall_score  = _safe_round(scores.get("context_recall"))

            available = [
                s for s in [
                    faithfulness_score,
                    answer_relevancy_score,
                    context_precision_score,
                    context_recall_score,
                ]
                if s is not None
            ]
            overall = round(sum(available) / len(available), 4) if available else None

            metrics = EvaluationMetrics(
                faithfulness=faithfulness_score,
                answer_relevancy=answer_relevancy_score,
                context_precision=context_precision_score,
                context_recall=context_recall_score,
                overall_score=overall,
            )

            logger.info(
                "[EvalService:%s] ✅ Selesai | faith=%.4f | rel=%.4f | prec=%s | rec=%s | overall=%s",
                source_label,
                faithfulness_score or 0.0,
                answer_relevancy_score or 0.0,
                f"{context_precision_score:.4f}" if context_precision_score else "N/A",
                f"{context_recall_score:.4f}" if context_recall_score else "N/A",
                f"{overall:.4f}" if overall else "N/A",
            )

            return EvaluationResponse(
                status="success",
                metrics=metrics,
                input=input_payload,
            )

        except Exception as exc:
            logger.error(
                "[EvalService:%s] ❌ Exception: %s",
                source_label,
                str(exc),
                exc_info=True,
            )
            return EvaluationResponse(
                status="error",
                error=str(exc),
                input=input_payload,
            )