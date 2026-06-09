"""
evaluator/app/core/llm_provider.py
"""

import logging
# UBAH: ganti import ChatGroq biasa dengan ThrottledChatGroq
# Sebelumnya: from langchain_groq import ChatGroq
from app.core.throttled_llm import ThrottledChatGroq          # ← BARU
from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    # UBAH: ganti ChatGroq(...) dengan ThrottledChatGroq(...)
    # Semua parameter sama persis, hanya class-nya yang berbeda
    llm = ThrottledChatGroq(                                   # ← UBAH
        temperature=settings.evaluator_llm_temperature,
        groq_api_key=settings.GROQ_API_KEY,
        model_name=settings.evaluator_llm_model,
    )
    logger.info(
        "✅ Evaluator LLM initialized (throttled): %s",
        settings.evaluator_llm_model
    )
except Exception as exc:
    logger.error("❌ Gagal inisialisasi evaluator LLM: %s", exc)
    llm = None