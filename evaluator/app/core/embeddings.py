"""
evaluator/app/core/embeddings.py

Embeddings provider khusus untuk evaluator service.
Menggunakan HuggingFace via langchain-huggingface versi 0.3.x.

PENTING: File ini menggunakan langchain 0.3.x — berbeda dari service utama.
"""

import logging
from langchain_huggingface import HuggingFaceEmbeddings
from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    embeddings = HuggingFaceEmbeddings(
        model_name=settings.evaluator_embedding_model,
        model_kwargs={"device": settings.evaluator_embedding_device},
    )
    logger.info("✅ Evaluator embeddings initialized: %s", settings.evaluator_embedding_model)
except Exception as exc:
    logger.error("❌ Gagal inisialisasi evaluator embeddings: %s", exc)
    embeddings = None