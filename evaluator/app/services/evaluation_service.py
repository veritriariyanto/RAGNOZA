"""
evaluator/app/services/evaluation_service.py

FIX #3 — Standarisasi path + efisiensi re-evaluasi ground truth.

MASALAH SEBELUMNYA:
    Ketika user input ground_truth (Path B / manual eval), evaluation_service
    menjalankan ULANG faithfulness + relevancy + risk_faithfulness yang sudah
    dihitung di Path A (auto eval). Ini membuang ~3 LLM call Groq per re-evaluasi.

SOLUSI:
    Tambahkan flag `is_reeval=True` di request.
    Jika is_reeval=True → skip faithfulness/relevancy/risk, hitung precision+recall saja.
    Hasil di-merge ke metrik existing dari DB (history_id wajib diisi).

ALUR YANG BENAR:
    Path A (otomatis setelah RAG):
        → faith + relevancy + risk_faithfulness
        → simpan ke DB

    Path B (user input ground_truth):
        → is_reeval=True + history_id wajib
        → hitung HANYA precision + recall
        → merge ke skor di DB (tidak overwrite faith/relevancy/risk)
"""

import logging
import asyncio
from typing import Optional

from app.schemas.evaluation_schemas import EvaluationMetrics, EvaluationResponse
from app.services.ragas_service import ragas_service

logger = logging.getLogger(__name__)

_TOTAL_FEATURES = 7
_eval_semaphore = asyncio.Semaphore(1)


def _compute_coverage(answer_faithfulness_segment: list[str]) -> float:
    feature_map = {
    "faithfulness": 4,  # Summary + Timeline + Comparison + Reference
    "qa": 2,            # ClauseSearch + LegalQA
    "risk": 1,          # RiskReview
}
    covered = sum(feature_map.get(s, 0) for s in answer_faithfulness_segment)
    return round(covered / _TOTAL_FEATURES, 4)

def _safe_round(val) -> Optional[float]:
    return round(float(val), 4) if val is not None else None


class EvaluationService:

    async def run_evaluation(
        self,
        question: str,
        context: str,
        answer: str,
        faithfulness_text: str,
        answer_qa: str,
        answer_risk: str,
        ground_truth: Optional[str] = None,
        source_label: str = "rag_pipeline",
        is_reeval: bool = False,
        # Metrik existing untuk di-merge saat is_reeval=True
        existing_faithfulness: Optional[float] = None,
        existing_answer_relevancy: Optional[float] = None,
        existing_risk_faithfulness: Optional[float] = None,
        existing_overall: Optional[float] = None,
        existing_segments: Optional[list] = None,
    ) -> EvaluationResponse:

        input_payload = {
            "question": question,
            "context": context[:200] + "..." if len(context) > 200 else context,
            "answer": answer[:200] + "..." if len(answer) > 200 else answer,
            "ground_truth": ground_truth,
            "answer_qa": answer_qa,   # ← tambah ini
            "source_label": source_label,
        }

        if not ragas_service.is_available:
            return EvaluationResponse(
                status="error",
                error="RAGAS service tidak tersedia",
                input=input_payload,
            )

        # Guard: is_reeval harus ada ground_truth
        if is_reeval and not ground_truth:
            return EvaluationResponse(
                status="error",
                error="is_reeval=True membutuhkan ground_truth. Isi ground_truth terlebih dahulu.",
                input=input_payload,
            )

        # Guard: semua segmen "-" hanya diblock saat bukan is_reeval
        if not is_reeval:
            all_placeholder = all(
                s.strip() in ("-", "", "None", "none")
                for s in [faithfulness_text, answer_qa, answer_risk]
            )
            if all_placeholder:
                return EvaluationResponse(
                    status="error",
                    error=(
                        "Semua segmen berisi placeholder '-'. "
                        "Gunakan endpoint /evaluation/ragas-auto-2metriks."
                    ),
                    input=input_payload,
                )

        try:
            import time
            wait_start = time.monotonic()
            logger.info("[EvalService:%s] Menunggu semaphore... (is_reeval=%s)", source_label, is_reeval)

            async with _eval_semaphore:
                wait_ms = (time.monotonic() - wait_start) * 1000
                logger.info(
                    "[EvalService:%s] Semaphore acquired setelah %.0fms. Mode: %s",
                    source_label, wait_ms,
                    "REEVAL (precision+recall saja)" if is_reeval else "FULL (semua metrik)",
                )

                # ─────────────────────────────────────────────────────────────
                # MODE A: REEVAL — hanya hitung precision + recall
                # Dipakai ketika user input ground_truth setelah auto eval selesai.
                # Faithfulness, relevancy, risk_faithfulness TIDAK diulang.
                # ─────────────────────────────────────────────────────────────
                if is_reeval:
                    return await self._run_reeval(
                        question=question,
                        context=context,
                        answer_qa=answer_qa,
                        ground_truth=ground_truth,
                        source_label=source_label,
                        input_payload=input_payload,
                        existing_faithfulness=existing_faithfulness,
                        existing_answer_relevancy=existing_answer_relevancy,
                        existing_risk_faithfulness=existing_risk_faithfulness,
                        existing_segments=existing_segments or [],
                    )

                # ─────────────────────────────────────────────────────────────
                # MODE B: FULL EVAL — semua metrik (Path A / auto eval)
                # ─────────────────────────────────────────────────────────────
                return await self._run_full_eval(
                    question=question,
                    context=context,
                    answer=answer,
                    faithfulness_text=faithfulness_text,
                    answer_qa=answer_qa,
                    answer_risk=answer_risk,
                    ground_truth=ground_truth,
                    source_label=source_label,
                    input_payload=input_payload,
                )

        except Exception as exc:
            logger.error("[EvalService:%s] Exception: %s", source_label, str(exc), exc_info=True)
            return EvaluationResponse(
                status="error",
                error=str(exc),
                input=input_payload,
            )

    # =========================================================================
    # HELPER: Full eval (dipakai Path A — auto eval)
    # =========================================================================

    async def _run_full_eval(
        self,
        question, 
        context, 
        answer,
        faithfulness_text, 
        answer_qa, 
        answer_risk,
        ground_truth, 
        source_label, 
        input_payload,
    ) -> EvaluationResponse:
        """
        Evaluasi lengkap: faithfulness (summary) + relevancy (qa) + risk_faithfulness (risk).
        Jika ground_truth ada, tambah precision + recall pada segmen QA.
        """
        evaluated_segments = []

        # JALUR 1: Summary → Faithfulness
        faithfulness_score = None
        if faithfulness_text.strip() not in ("-", "", "None", "none"):
            logger.info("[EvalService][full] [1/3] Faithfulness segmen summary...")
            result = await ragas_service.evaluate_rag_custom(
                question=question,
                context=context,
                answer=faithfulness_text,
                metric_types=["faithfulness"],
                ground_truth=ground_truth,
            )
            faithfulness_score = result.to_pandas().to_dict(orient="records")[0].get("faithfulness")
            evaluated_segments.append("faithfulness")

        # JALUR 2: QA → Relevancy (+ precision/recall jika ada GT)
        answer_relevancy_score = context_precision_score = context_recall_score = None
        if answer_qa.strip() not in ("-", "", "None"):
            logger.info("[EvalService][full] [2/3] Relevancy segmen QA...")
            metric_types = ["answer_relevancy"]
            if ground_truth:
                metric_types.extend(["context_precision", "context_recall"])

            result = await ragas_service.evaluate_rag_custom(
                question=question, context=context, answer=answer_qa,
                metric_types=metric_types, ground_truth=ground_truth,
            )
            scores = result.to_pandas().to_dict(orient="records")[0]
            answer_relevancy_score   = scores.get("answer_relevancy")
            context_precision_score  = scores.get("context_precision")
            context_recall_score     = scores.get("context_recall")
            evaluated_segments.append("qa")

        # JALUR 3: Risk → Faithfulness (FIX #2)
        risk_faithfulness_score = None
        if answer_risk.strip() not in ("-", "", "None"):
            logger.info("[EvalService][full] [3/3] Faithfulness segmen risk...")
            result = await ragas_service.evaluate_rag_custom(
                question=question, context=context, answer=answer_risk,
                metric_types=["faithfulness"], ground_truth=ground_truth,
            )
            risk_faithfulness_score = result.to_pandas().to_dict(orient="records")[0].get("faithfulness")
            evaluated_segments.append("risk")

            if risk_faithfulness_score is not None and risk_faithfulness_score < 0.6:
                logger.warning(
                    "[EvalService:%s] PERINGATAN risk_faithfulness=%.4f < 0.6",
                    source_label, risk_faithfulness_score,
                )
        

        # Rekapitulasi
        f  = _safe_round(faithfulness_score)
        r  = _safe_round(answer_relevancy_score)
        p  = _safe_round(context_precision_score)
        c  = _safe_round(context_recall_score)
        rf = _safe_round(risk_faithfulness_score)

        available = [s for s in [f, r, p, c, rf] if s is not None]
        overall   = round(sum(available) / len(available), 4) if available else None
        coverage  = _compute_coverage(evaluated_segments)

        logger.info(
            "[EvalService:%s][full] faith=%.4f | rel=%.4f | risk_faith=%.4f | "
            "prec=%s | rec=%s | overall=%s | cov=%.0f%%",
            source_label,
            f or 0, r or 0, rf or 0,
            f"{p:.4f}" if p else "N/A",
            f"{c:.4f}" if c else "N/A",
            f"{overall:.4f}" if overall else "N/A",
            (coverage * 100),
        )

        return EvaluationResponse(
            status="success",
            metrics=EvaluationMetrics(
                faithfulness=f,
                answer_relevancy=r,
                context_precision=p,
                context_recall=c,
                risk_faithfulness=rf,
                overall_score=overall,
                answer_faithfulness_segment=evaluated_segments,
                coverage_pct=coverage,
            ),
            input=input_payload,
        )

    # =========================================================================
    # HELPER: Re-eval (dipakai Path B — user input ground truth)
    # =========================================================================

    async def _run_reeval(
        self,
        question, 
        context, 
        answer_qa, 
        ground_truth,
        source_label, 
        input_payload,
        existing_faithfulness, 
        existing_answer_relevancy,
        existing_risk_faithfulness, 
        existing_segments,
    ) -> EvaluationResponse:
        """
        Re-evaluasi EFISIEN: hanya hitung context_precision + context_recall.
        Faithfulness, relevancy, risk_faithfulness diambil dari existing (sudah ada di DB).

        Menghemat ~3 LLM call Groq dibanding menjalankan ulang semua metrik.
        """
        logger.info(
            "[EvalService:%s][reeval] Hitung precision+recall saja (GT tersedia). "
            "faith/relevancy/risk diambil dari existing.",
            source_label,
        )

        context_precision_score = context_recall_score = None

        if answer_qa.strip() not in ("-", "", "None"):
            result = await ragas_service.evaluate_rag_custom(
                question=question,
                context=context,
                answer=answer_qa,
                metric_types=["context_precision", "context_recall"],
                ground_truth=ground_truth,
            )
            scores = result.to_pandas().to_dict(orient="records")[0]
            context_precision_score = scores.get("context_precision")
            context_recall_score    = scores.get("context_recall")
        else:
            logger.warning("[EvalService][reeval] answer_qa kosong — precision/recall dilewati.")

        p  = _safe_round(context_precision_score)
        c  = _safe_round(context_recall_score)
        f  = _safe_round(existing_faithfulness)
        r  = _safe_round(existing_answer_relevancy)
        rf = _safe_round(existing_risk_faithfulness)

        # Overall dihitung ulang dari SEMUA metrik yang tersedia (merged)
        available = [s for s in [f, r, p, c, rf] if s is not None]
        overall   = round(sum(available) / len(available), 4) if available else None
        coverage  = _compute_coverage(existing_segments)

        logger.info(
            "[EvalService:%s][reeval] prec=%.4f | rec=%.4f | "
            "overall_merged=%.4f | (faith/rel/risk dari existing)",
            source_label,
            p or 0, c or 0,
            overall or 0,
        )

        return EvaluationResponse(
            status="success",
            metrics=EvaluationMetrics(
                faithfulness=f,
                answer_relevancy=r,
                context_precision=p,
                context_recall=c,
                risk_faithfulness=rf,
                overall_score=overall,
                answer_faithfulness_segment=existing_segments,
                coverage_pct=coverage,
            ),
            input=input_payload,
        )


evaluation_service = EvaluationService()