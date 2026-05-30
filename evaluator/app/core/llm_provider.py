"""
evaluator/app/core/llm_provider.py

LLM provider khusus untuk evaluator service.
Menggunakan Groq via langchain-groq versi 0.3.x (kompatibel dengan ragas).

PENTING: File ini menggunakan langchain 0.3.x — berbeda dari service utama.
         Jangan import apapun dari app/ (service utama) di sini.
"""

import logging
from langchain_groq import ChatGroq
from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    llm = ChatGroq(
        temperature=settings.evaluator_llm_temperature,
        groq_api_key=settings.GROQ_API_KEY,
        model_name=settings.evaluator_llm_model,
    )
    logger.info("✅ Evaluator LLM initialized: %s", settings.evaluator_llm_model)
except Exception as exc:
    logger.error("❌ Gagal inisialisasi evaluator LLM: %s", exc)
    llm = None