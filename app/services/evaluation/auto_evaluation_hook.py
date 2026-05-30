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

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# URL evaluator service — baca dari env var, default ke docker service name
EVALUATOR_BASE_URL = os.getenv("EVALUATOR_URL", "http://localhost:8001")
EVALUATOR_ENDPOINT = f"{EVALUATOR_BASE_URL}/api/v1/evaluate"

# Timeout cukup panjang karena RAGAS memanggil LLM beberapa kali
EVALUATOR_TIMEOUT = float(os.getenv("EVALUATOR_TIMEOUT_SECONDS", "120"))


async def trigger_auto_evaluation(
    question: str,
    context: str,
    answer: str,
    ground_truth: Optional[str] = None,
    source_label: str = "rag_pipeline",
) -> dict:
    """
    Kirim request evaluasi ke evaluator service (port 8001) secara async.

    Dipanggil sebagai BackgroundTask dari route — tidak memblokir response user.
    Seluruh logika ragas ada di evaluator service, bukan di sini.

    Args:
        question     : Pertanyaan asli user (setelah repair jika ada)
        context      : Gabungan context yang di-retrieve dari Qdrant
        answer       : Jawaban final LLM
        ground_truth : (Opsional) Proxy ground truth
        source_label : Label sumber untuk logging

    Returns:
        dict hasil evaluasi dari evaluator service, atau dict error jika gagal
    """
    logger.info(
        "[AutoEval:%s] Mengirim ke evaluator service | q=%d | ctx=%d | ans=%d",
        source_label,
        len(question),
        len(context),
        len(answer),
    )

    payload = {
        "question": question,
        "context": context,
        "answer": answer,
        "ground_truth": ground_truth,
        "source_label": source_label,
    }

    try:
        async with httpx.AsyncClient(timeout=EVALUATOR_TIMEOUT) as client:
            response = await client.post(EVALUATOR_ENDPOINT, json=payload)
            response.raise_for_status()
            result = response.json()

        if result.get("status") == "success":
            metrics = result.get("metrics") or {}
            logger.info(
                "[AutoEval:%s] ✅ Evaluasi selesai | "
                "faithfulness=%.4f | answer_relevancy=%.4f | "
                "context_precision=%s | context_recall=%s | overall=%s",
                source_label,
                metrics.get("faithfulness") or 0.0,
                metrics.get("answer_relevancy") or 0.0,
                f"{metrics['context_precision']:.4f}" if metrics.get("context_precision") else "N/A",
                f"{metrics['context_recall']:.4f}" if metrics.get("context_recall") else "N/A",
                f"{metrics['overall_score']:.4f}" if metrics.get("overall_score") else "N/A",
            )
        else:
            logger.warning(
                "[AutoEval:%s] ⚠️ Evaluator mengembalikan error: %s",
                source_label,
                result.get("error"),
            )

        return result

    except httpx.ConnectError:
        # Evaluator service tidak jalan — jangan crash service utama
        logger.warning(
            "[AutoEval:%s] ⚠️ Evaluator service tidak dapat dijangkau (%s). "
            "Pastikan container evaluator berjalan.",
            source_label,
            EVALUATOR_ENDPOINT,
        )
        return {
            "status": "error",
            "error": "Evaluator service tidak dapat dijangkau",
            "metrics": None,
        }

    except httpx.TimeoutException:
        logger.warning(
            "[AutoEval:%s] ⚠️ Evaluator service timeout setelah %.0fs",
            source_label,
            EVALUATOR_TIMEOUT,
        )
        return {
            "status": "error",
            "error": f"Evaluator timeout setelah {EVALUATOR_TIMEOUT}s",
            "metrics": None,
        }

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
        }