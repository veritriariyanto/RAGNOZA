"""
auto_evaluation_hook.py

Modul ini bertanggung jawab menjalankan evaluasi RAGAS secara otomatis
di background setelah RAG pipeline selesai menjawab pertanyaan user.

Alur:
    User Question
         ↓
    RAG Pipeline (STT → Repair → Search → LLM)
         ↓
    answer + context tersedia
         ↓
    ┌─── return response ke user  (tidak blocking)
    └─── trigger_auto_evaluation() → RAGAS → log hasil
"""

import logging
import json
from typing import Optional

logger = logging.getLogger(__name__)


async def trigger_auto_evaluation(
    question: str,
    context: str,
    answer: str,
    ground_truth: Optional[str] = None,
    source_label: str = "rag_pipeline",
) -> dict:
    """
    Jalankan evaluasi RAGAS secara async.

    Dipanggil sebagai background task dari route — tidak memblokir response.

    Args:
        question     : Pertanyaan asli user (setelah repair jika ada)
        context      : Gabungan context yang di-retrieve dari Qdrant
        answer       : Jawaban final LLM / material yang di-generate
        ground_truth : (Opsional) Proxy ground truth — jika None, pakai
                       context pertama sebagai ground truth otomatis
        source_label : Label sumber untuk logging (misal: "audio_rag", "text_rag")

    Returns:
        dict hasil evaluasi, atau dict error jika gagal
    """
    # Import di dalam fungsi agar tidak circular import
    from app.services.evaluation.evaluation_service import EvaluationService

    evaluation_service = EvaluationService()

    # Jika ground_truth tidak disediakan, gunakan context sebagai proxy.
    # Ini praktik umum di production RAGAS karena ground truth jarang tersedia real-time.
    effective_ground_truth = ground_truth
    if not effective_ground_truth and context:
        # Ambil kalimat pertama dari context sebagai proxy ground truth
        first_sentence = context.split("\n\n")[0].strip()
        effective_ground_truth = first_sentence if first_sentence else context[:500]
        logger.info(
            "[AutoEval:%s] Ground truth tidak ada → pakai context pertama sebagai proxy",
            source_label,
        )

    logger.info(
        "[AutoEval:%s] Memulai evaluasi RAGAS | question_len=%d | context_len=%d | answer_len=%d",
        source_label,
        len(question),
        len(context),
        len(answer),
    )

    try:
        result = await evaluation_service.run_evaluation(
            question=question,
            context=context,
            answer=answer,
            ground_truth=effective_ground_truth,
        )

        if result["status"] == "success":
            metrics = result.get("metrics", {})
            logger.info(
                "[AutoEval:%s] ✅ RAGAS selesai | "
                "faithfulness=%.4f | answer_relevancy=%.4f | "
                "context_precision=%.4f | context_recall=%.4f | overall=%.4f",
                source_label,
                metrics.get("faithfulness") or 0.0,
                metrics.get("answer_relevancy") or 0.0,
                metrics.get("context_precision") or 0.0,
                metrics.get("context_recall") or 0.0,
                metrics.get("overall_score") or 0.0,
            )
        else:
            logger.warning(
                "[AutoEval:%s] ⚠️ Evaluasi gagal: %s",
                source_label,
                result.get("error"),
            )

        print("\n=== RAGAS RESULT ===")
        print(json.dumps(result, indent=4, ensure_ascii=False))

        return result

    except Exception as exc:
        logger.error(
            "[AutoEval:%s] ❌ Exception saat evaluasi: %s",
            source_label,
            str(exc),
            exc_info=True,
        )
        return {
            "status": "error",
            "error": str(exc),
            "metrics": None,
            "input": {
                "question": question,
                "context": context,
                "answer": answer,
                "ground_truth": effective_ground_truth,
            },
        }