"""
app/services/evaluation/auto_evaluation_hook.py

Modul ini menjalankan evaluasi RAGAS secara otomatis di background setelah
RAG pipeline selesai menjawab pertanyaan user.

PERUBAHAN ARSITEKTUR:
    Sebelumnya → import langsung EvaluationService (menyebabkan konflik ragas vs langchain)
    Sekarang   → HTTP POST ke evaluator service (port 8001) via httpx

Alur:
    User Question
         ↓
    RAG Pipeline (STT → Repair → Search → LLM)
         ↓
    answer + context tersedia
         ↓
    ┌─── return response ke user  (tidak blocking)
    └─── trigger_auto_evaluation()
              ↓
         HTTP POST → evaluator:8001/api/v1/evaluate  (background task)
              ↓
         Hasil RAGAS di-log (dan bisa disimpan ke DB jika diperlukan)
"""

# app/services/evaluation/auto_evaluation_hook.py

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

EVALUATOR_BASE_URL = os.getenv("EVALUATOR_URL", "http://localhost:8001")
EVALUATOR_ENDPOINT = f"{EVALUATOR_BASE_URL}/api/v1/evaluate"
# Auto-eval bisa ikut antre di semaphore evaluator, jadi timeout perlu cukup longgar.
EVALUATOR_TIMEOUT  = float(os.getenv("EVALUATOR_TIMEOUT_SECONDS", "900"))


async def _call_evaluator(payload: dict, source_label: str) -> dict:
    """HTTP POST ke evaluator service, return hasil atau dict error."""
    try:
        async with httpx.AsyncClient(timeout=EVALUATOR_TIMEOUT) as client:
            response = await client.post(EVALUATOR_ENDPOINT, json=payload)
            response.raise_for_status()
            return response.json()

    except httpx.ConnectError:
        logger.warning(
            "[AutoEval:%s] Evaluator tidak dapat dijangkau (%s).",
            source_label, EVALUATOR_ENDPOINT,
        )
        return {"status": "error", "error": "Evaluator service tidak dapat dijangkau", "metrics": None}

    except httpx.TimeoutException:
        logger.warning(
            "[AutoEval:%s] Evaluator timeout setelah %.0fs", source_label, EVALUATOR_TIMEOUT,
        )
        return {"status": "error", "error": f"Evaluator timeout setelah {EVALUATOR_TIMEOUT}s", "metrics": None}

    except Exception as exc:
        logger.error("[AutoEval:%s] Exception: %s", source_label, exc, exc_info=True)
        return {"status": "error", "error": str(exc), "metrics": None}


def _update_ragas_in_db(history_id: int, result: dict) -> None:
    """
    Buka DB session BARU (bukan dari request) khusus untuk background task.
    Session request sudah tidak valid saat background task berjalan.
    """
    try:
        from app.core.postgres import SessionLocal
        from app.services.history.rag_history_service import RAGHistoryService

        with SessionLocal() as db:
            RAGHistoryService.update_ragas(
                db=db,
                history_id=history_id,
                ragas_result=result,
            )
    except Exception as exc:
        logger.error(
            "[AutoEval] Gagal update RAGAS ke DB (history_id=%s): %s",
            history_id, exc, exc_info=True,
        )


async def trigger_auto_evaluation(
    question: str,
    context: str,
    answer: str,
    ground_truth: Optional[str] = None,
    source_label: str = "rag_pipeline",
    history_id: Optional[int] = None,
    # CATATAN: jangan terima 'db' dari request — buat session baru di dalam
) -> dict:
    """
    Kirim request evaluasi ke evaluator service (port 8001) secara async.
    Jika history_id diberikan, update baris DB yang sama setelah evaluasi selesai.

    PENTING: db session TIDAK diteruskan dari request karena sudah closed
    saat background task berjalan. Gunakan SessionLocal() baru di dalam.
    """
    logger.info(
        "[AutoEval:%s] Mengirim ke evaluator | q=%d chars | ctx=%d chars | ans=%d chars",
        source_label, len(question), len(context), len(answer),
    )

    payload = {
        "question": question,
        "context": context,
        "answer": answer,
        "ground_truth": ground_truth,
        "source_label": source_label,
    }

    result = await _call_evaluator(payload, source_label)

    # ── Log hasil ──────────────────────────────────────────────────────────
    if result.get("status") == "success":
        metrics = result.get("metrics") or {}
        logger.info(
            "[AutoEval:%s] ✅ Selesai | faith=%.4f | relevancy=%.4f | "
            "precision=%s | recall=%s | overall=%s",
            source_label,
            metrics.get("faithfulness") or 0.0,
            metrics.get("answer_relevancy") or 0.0,
            f"{metrics['context_precision']:.4f}" if metrics.get("context_precision") else "N/A",
            f"{metrics['context_recall']:.4f}"    if metrics.get("context_recall")    else "N/A",
            f"{metrics['overall_score']:.4f}"     if metrics.get("overall_score")     else "N/A",
        )
    else:
        logger.warning(
            "[AutoEval:%s] ⚠️ Error dari evaluator: %s",
            source_label, result.get("error"),
        )

    # ── Update DB jika history_id tersedia ────────────────────────────────
    if history_id is not None:
        _update_ragas_in_db(history_id, result)
    else:
        logger.debug("[AutoEval:%s] history_id tidak ada — DB tidak diupdate.", source_label)

    return result