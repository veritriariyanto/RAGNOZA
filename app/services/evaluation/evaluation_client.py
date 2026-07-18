#app/services/evaluation/evaluation_client.py

import logging
import os

import httpx

logger = logging.getLogger(__name__)

EVALUATOR_BASE_URL = os.getenv("EVALUATOR_URL", "http://localhost:8001")
EVALUATOR_ENDPOINT = f"{EVALUATOR_BASE_URL}/api/v1/evaluate"
# Auto-eval bisa ikut antre di semaphore evaluator, jadi timeout perlu cukup longgar.
EVALUATOR_TIMEOUT  = float(os.getenv("EVALUATOR_TIMEOUT_SECONDS", "900"))

# =============================================================================
# HELPER FUNCTIONS (Fungsi Internal)
# =============================================================================

async def call_evaluator(payload: dict, source_label: str) -> dict:
    """
    Fungsi Asinkron untuk melakukan HTTP POST Request ke service Evaluator (:8001).
    Fungsi ini dirancang agar 'safe-fail' (tidak melempar HTTPException yang membuat aplikasi mati), 
    melainkan menangkap error jaringan dan mengembalikannya dalam bentuk dictionary berstatus 'error'.
    """
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
