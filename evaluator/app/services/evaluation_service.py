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

FIX #8 — Efisiensi dataset_eval_reference (skip_answer_relevancy).
    MASALAH: dataset_eval_reference menjalankan _run_full_eval dari nol,
    termasuk menghitung ulang answer_relevancy — padahal question & answer
    IDENTIK dengan dataset_eval_live (hanya context yang beda), dan
    answer_relevancy tidak bergantung pada context sama sekali. Ini membuang
    ~3 LLM call/soal tanpa nilai tambah (hasilnya pasti sama).

    SOLUSI: flag `skip_answer_relevancy=True` + `existing_answer_relevancy`.
    Beda dengan is_reeval (skip faithfulness+relevancy+risk semua), di sini
    HANYA answer_relevancy yang di-skip — faithfulness_summary/qa, risk,
    precision, recall tetap dihitung penuh karena memang bergantung context.
"""

import logging
import asyncio
import math
from typing import Optional

from app.schemas.evaluation_schemas import EvaluationMetrics, EvaluationResponse
from app.services.ragas_service import ragas_service

logger = logging.getLogger(__name__)

logging.getLogger("ragas").setLevel(logging.DEBUG)

_eval_semaphore = asyncio.Semaphore(1)

def _safe_round(val) -> Optional[float]:
    """
    FIX: RAGAS evaluate() tidak melempar exception saat satu baris gagal
    (mis. rate limit di tengah eksekusi) — ia mengisi sel yang gagal dengan
    float('nan'), BUKAN None. Tanpa isnan() check, NaN lolos ke DB dan
    meracuni AVG()/agregat SQL (AVG dengan 1 baris NaN → seluruh hasil NaN,
    beda dengan NULL yang otomatis diabaikan fungsi agregat).
    """
    if val is None:
        return None
    val = float(val)
    if math.isnan(val):
        return None
    return round(val, 4)

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
        context_chunks: Optional[list[str]] = None,
        existing_faithfulness_summary: Optional[float] = None,   # ← FIX #7 (Prioritas 4)
        existing_faithfulness_qa: Optional[float] = None,        # ← FIX #7 (Prioritas 4)
        skip_answer_relevancy: bool = False,                     # ← FIX #8
    ) -> EvaluationResponse:

        input_payload = {
            "question": question,
            "context": context[:200] + "..." if len(context) > 200 else context,
            "answer": answer[:200] + "..." if len(answer) > 200 else answer,
            "ground_truth": ground_truth,
            "answer_qa": answer_qa,   # ← tambah ini
            "source_label": source_label,
            # FIX #Fase0-2 (M13): simpan teks penuh (TIDAK dipotong seperti context/answer di atas),
            # karena ini yang benar-benar dinilai LLM judge dan wajib bisa ditelusuri ulang.
            "faithfulness_text": faithfulness_text,
            "answer_risk": answer_risk,
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

        # FIX #8 — Guard: skip_answer_relevancy butuh existing_answer_relevancy,
        # kalau tidak ada tidak masuk akal untuk di-skip (tidak ada nilai pengganti).
        if skip_answer_relevancy and existing_answer_relevancy is None:
            logger.warning(
                "[EvalService:%s] skip_answer_relevancy=True tapi existing_answer_relevancy "
                "kosong — answer_relevancy akan tetap dihitung ulang sebagai fallback aman.",
                source_label,
            )
            skip_answer_relevancy = False

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
                        context_chunks=context_chunks,
                        faithfulness_text=faithfulness_text,   # ← FIX #5 (Prioritas 2)
                        existing_faithfulness_summary=existing_faithfulness_summary,   # ← baru
                        existing_faithfulness_qa=existing_faithfulness_qa,
                    )

                # ─────────────────────────────────────────────────────────────
                # MODE B: FULL EVAL — semua metrik (Path A / auto eval)
                # FIX #8: skip_answer_relevancy bisa mengurangi 1 metrik di
                # dalam mode ini tanpa mengubah metrik lain (beda dengan is_reeval).
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
                    context_chunks=context_chunks,
                    skip_answer_relevancy=skip_answer_relevancy,           # ← FIX #8
                    existing_answer_relevancy=existing_answer_relevancy,   # ← FIX #8
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
        context_chunks: Optional[list[str]] = None, 
        skip_answer_relevancy: bool = False,                      # ← FIX #8
        existing_answer_relevancy: Optional[float] = None,        # ← FIX #8
    ) -> EvaluationResponse:
        """
        Evaluasi lengkap: faithfulness (summary) + relevancy (qa) + risk_faithfulness (risk).
        Jika ground_truth ada, tambah precision + recall pada segmen QA.

        FIX #8: jika skip_answer_relevancy=True, JALUR 2 hanya menghitung
        faithfulness segmen QA (1 metrik, bukan 2) — answer_relevancy diambil
        dari existing_answer_relevancy tanpa panggilan LLM tambahan. Berguna
        saat question & answer identik dengan evaluasi sebelumnya dan hanya
        context yang berubah (relevancy tidak bergantung context).
        """
        evaluated_segments = []

        # FIX (Merge/Parallelize Evaluation Call): sebelumnya 3 segmen (summary,
        # qa, risk) dipanggil berurutan dengan `await` satu-satu — total waktu
        # tunggu = jumlah waktu ketiganya. Throttle TPM sudah global & thread-safe
        # (lihat throttled_llm.py), jadi ketiganya aman dijalankan BERSAMAAN via
        # asyncio.gather — throttle tetap menjaga total token/menit, tapi ketiganya
        # tidak lagi saling menunggu selesai total sebelum yang berikutnya mulai.
        #
        # Precision/Recall (2b) TETAP menunggu hasil QA/Summary selesai dulu,
        # karena basis teksnya (pr_basis_text) baru diketahui setelah itu.

        # ROLLBACK: paralelisasi 3 segmen terbukti regresi (lihat catatan di
        # ragas_service.py _ragas_executor). Kembali serial.

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
                context_chunks=context_chunks,
            )
            faithfulness_score = result.to_pandas().to_dict(orient="records")[0].get("faithfulness")
            evaluated_segments.append("faithfulness")

        # JALUR 2: QA → Faithfulness (+ Relevancy, kecuali di-skip) (context PENUH)
        answer_relevancy_score = qa_faithfulness_score = None
        if answer_qa.strip() not in ("-", "", "None"):
            if skip_answer_relevancy:
                # FIX #8: hanya faithfulness_qa yang dihitung — 1 metrik saja,
                # bukan 2 — answer_relevancy di-reuse dari evaluasi sebelumnya.
                logger.info(
                    "[EvalService][full] [2/3] Faithfulness segmen QA saja "
                    "(answer_relevancy di-reuse=%.4f, tidak dihitung ulang)...",
                    existing_answer_relevancy or 0.0,
                )
                result = await ragas_service.evaluate_rag_custom(
                    question=question,
                    context=context,
                    answer=answer_qa,
                    metric_types=["faithfulness"],
                    ground_truth=ground_truth,
                    context_chunks=None,
                )
                scores = result.to_pandas().to_dict(orient="records")[0]
                qa_faithfulness_score  = scores.get("faithfulness")
                answer_relevancy_score = existing_answer_relevancy
            else:
                logger.info("[EvalService][full] [2/3] Faithfulness + Relevancy segmen QA (context penuh)...")
                result = await ragas_service.evaluate_rag_custom(
                    question=question,
                    context=context,
                    answer=answer_qa,
                    metric_types=["faithfulness", "answer_relevancy"],
                    ground_truth=ground_truth,
                    context_chunks=None,
                )
                scores = result.to_pandas().to_dict(orient="records")[0]
                qa_faithfulness_score  = scores.get("faithfulness")
                answer_relevancy_score = scores.get("answer_relevancy")
            evaluated_segments.append("qa")

        context_precision_score = context_recall_score = None
        if ground_truth:
            pr_basis_text = None
            pr_basis_label = None
            if answer_qa.strip() not in ("-", "", "None"):
                pr_basis_text = answer_qa
                pr_basis_label = "qa"
            elif faithfulness_text.strip() not in ("-", "", "None", "none"):
                pr_basis_text = faithfulness_text
                pr_basis_label = "summary"

            if pr_basis_text:
                logger.info(
                    "[EvalService][full] [2b] Context Precision + Recall (basis=%s, chunk granular)...",
                    pr_basis_label,
                )
                pr_result = await ragas_service.evaluate_rag_custom(
                    question=question,
                    context=context,
                    answer=pr_basis_text,
                    metric_types=["context_precision", "context_recall"],
                    ground_truth=ground_truth,
                    context_chunks=context_chunks,
                )
                pr_scores = pr_result.to_pandas().to_dict(orient="records")[0]
                context_precision_score = pr_scores.get("context_precision")
                context_recall_score    = pr_scores.get("context_recall")
            else:
                logger.warning(
                    "[EvalService:%s][full] Precision/Recall dilewati — semua segmen (qa & summary) kosong.",
                    source_label,
                )

        # JALUR 3: Risk → Faithfulness (FIX #2)
        risk_faithfulness_score = None
        if answer_risk.strip() not in ("-", "", "None"):
            logger.info("[EvalService][full] [3/3] Faithfulness segmen risk...")
            result = await ragas_service.evaluate_rag_custom(
                question=question, 
                context=context,
                answer=answer_risk,
                metric_types=["faithfulness"],
                ground_truth=ground_truth,
                context_chunks=context_chunks,
            )
            risk_faithfulness_score = result.to_pandas().to_dict(orient="records")[0].get("faithfulness")
            evaluated_segments.append("risk")

            if risk_faithfulness_score is not None and risk_faithfulness_score < 0.6:
                logger.warning(
                    "[EvalService:%s] PERINGATAN risk_faithfulness=%.4f < 0.6",
                    source_label, risk_faithfulness_score,
                )
        
        # FIX #Fase0-1: faithfulness gabungan DIHAPUS (bukan lagi rata-rata summary+qa).
        # Skor per-segmen (faithfulness_summary, faithfulness_qa) sekarang adalah
        # satu-satunya sumber kebenaran — rata-rata menyembunyikan segmen yang buruk.
        # Field `faithfulness` dipertahankan di schema untuk backward compatibility,
        # tapi TIDAK diisi lagi di sini (selalu None dari full eval).
        f = None

        r  = _safe_round(answer_relevancy_score)
        p  = _safe_round(context_precision_score)
        c  = _safe_round(context_recall_score)
        rf = _safe_round(risk_faithfulness_score)

        f_summary = _safe_round(faithfulness_score)
        f_qa      = _safe_round(qa_faithfulness_score)

        logger.info(
            "[EvalService:%s][full] faith_summary=%s | faith_qa=%s | rel=%.4f%s | risk_faith=%s | "
            "prec=%s | rec=%s",
            source_label,
            f"{f_summary:.4f}" if f_summary is not None else "N/A",
            f"{f_qa:.4f}" if f_qa is not None else "N/A",
            r or 0,
            " (reused)" if skip_answer_relevancy else "",
            f"{rf:.4f}" if rf is not None else "N/A",   # FIX: None ≠ 0.0 — jangan disamakan
            f"{p:.4f}" if p else "N/A",
            f"{c:.4f}" if c else "N/A",
        )

        return EvaluationResponse(
            status="success",
            metrics=EvaluationMetrics(
                faithfulness=f,
                answer_relevancy=r,
                context_precision=p,
                context_recall=c,
                risk_faithfulness=rf,
                answer_faithfulness_segment=evaluated_segments,
                faithfulness_summary=f_summary,   # ← baru
                faithfulness_qa=f_qa,             # ← baru
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
        context_chunks: Optional[list[str]] = None,
        faithfulness_text: Optional[str] = None,   # ← FIX #5 (Prioritas 2): basis fallback
        existing_faithfulness_summary: Optional[float] = None,   # ← FIX #7 (Prioritas 4)
        existing_faithfulness_qa: Optional[float] = None,        # ← FIX #7 (Prioritas 4)
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

        # FIX #5 (Prioritas 2): fallback berjenjang, sama seperti di _run_full_eval
        reeval_basis_text = None
        reeval_basis_label = None
        if answer_qa.strip() not in ("-", "", "None"):
            reeval_basis_text = answer_qa
            reeval_basis_label = "qa"
        elif faithfulness_text and faithfulness_text.strip() not in ("-", "", "None", "none"):
            reeval_basis_text = faithfulness_text
            reeval_basis_label = "summary"

        if reeval_basis_text:
            logger.info(
                "[EvalService][reeval] Basis precision/recall: %s",
                reeval_basis_label,
            )
            result = await ragas_service.evaluate_rag_custom(
                question=question,
                context=context,
                answer=reeval_basis_text,
                metric_types=["context_precision", "context_recall"],
                ground_truth=ground_truth,
                context_chunks=context_chunks,
            )
            scores = result.to_pandas().to_dict(orient="records")[0]
            context_precision_score = scores.get("context_precision")
            context_recall_score    = scores.get("context_recall")
        else:
            logger.warning(
                "[EvalService][reeval] Semua segmen (qa & summary) kosong — precision/recall dilewati."
            )

        p  = _safe_round(context_precision_score)
        c  = _safe_round(context_recall_score)
        f  = None
        r  = _safe_round(existing_answer_relevancy)
        rf = _safe_round(existing_risk_faithfulness)

        # FIX #7 (Prioritas 4): sekadar diteruskan dari existing, tidak dihitung ulang
        f_summary = _safe_round(existing_faithfulness_summary)
        f_qa      = _safe_round(existing_faithfulness_qa)

        merged_segments = list(set(existing_segments + ([reeval_basis_label] if reeval_basis_label else [])))

        logger.info(
            "[EvalService:%s][reeval] prec=%.4f | rec=%.4f | "
            "(faith/rel/risk dari existing)",
            source_label,
            p or 0, c or 0,
        )

        return EvaluationResponse(
            status="success",
            metrics=EvaluationMetrics(
                faithfulness=f,
                answer_relevancy=r,
                context_precision=p,
                context_recall=c,
                risk_faithfulness=rf,
                answer_faithfulness_segment=merged_segments,
                faithfulness_summary=f_summary,   # ← baru
                faithfulness_qa=f_qa,             # ← baru
            ),
            input=input_payload,
        )


evaluation_service = EvaluationService()