"""
evaluator/app/core/llm_provider.py
"""

import logging
from app.core.throttled_llm import ThrottledChatGroq
from app.core.config import settings

logger = logging.getLogger(__name__)

# Inisialisasi awal variabel llm
llm = None

try:
    # UPDATE: Mengubah properti settings menjadi HURUF BESAR
    llm = ThrottledChatGroq(
        temperature=settings.EVALUATOR_LLM_TEMPERATURE,
        groq_api_key=settings.GROQ_API_KEY,
        model_name=settings.EVALUATOR_LLM_MODEL,
    )
    logger.info(
        "✅ Evaluator LLM initialized (throttled): %s",
        settings.EVALUATOR_LLM_MODEL
    )
except Exception as exc:
    logger.error("❌ Gagal inisialisasi evaluator LLM: %s", exc)
    llm = None