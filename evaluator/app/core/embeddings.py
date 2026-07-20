"""
evaluator/app/core/embeddings.py

Embeddings provider khusus untuk evaluator service.
Menggunakan HuggingFace via langchain-huggingface versi 0.3.x.
"""

import logging
from langchain_huggingface import HuggingFaceEmbeddings
from app.core.config import settings

logger = logging.getLogger(__name__)

# Inisialisasi variabel di luar blok try-except
embeddings = None

try:
    # UPDATE: Mengubah variabel setting menjadi HURUF BESAR sesuai config.py terbaru
    embeddings = HuggingFaceEmbeddings(
        model_name=settings.EVALUATOR_EMBEDDING_MODEL,
        model_kwargs={"device": settings.EVALUATOR_EMBEDDING_DEVICE},
    )
    logger.info("✅ Evaluator embeddings initialized: %s", settings.EVALUATOR_EMBEDDING_MODEL)
except Exception as exc:
    logger.error("❌ Gagal inisialisasi evaluator embeddings: %s", exc)
    # Tetap None, namun service yang menggunakan variabel ini harus siap menangani kondisi None.
    embeddings = None