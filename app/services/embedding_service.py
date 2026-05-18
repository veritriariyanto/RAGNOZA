"""
app/services/embedding_service.py
===================================
Embedding service menggunakan SentenceTransformers.

Fitur:
- Lazy loading model (dimuat pertama kali saat dipakai)
- Async-safe: encode dijalankan di thread pool agar tidak block event loop
- Normalize embeddings (cosine similarity ready)
- Batch processing dengan progress bar untuk dataset besar

Model default: paraphrase-multilingual-MiniLM-L12-v2
  - Mendukung 50+ bahasa termasuk Indonesia
  - Dimensi: 384
  - Kecepatan: cepat (cocok untuk CPU)
"""

import asyncio
import logging
from functools import cached_property
from typing import Optional

logger = logging.getLogger(__name__)

from app.config import settings
from app.models.schemas import DocumentChunk


class EmbeddingService:
    """
    Wrapper di atas SentenceTransformer untuk embed teks dan chunks.

    Penggunaan:
        svc = EmbeddingService()
        vector = svc.embed_text("Pasal 1 ayat 1 berbunyi...")
        chunks  = await svc.embed_chunks(list_of_chunks)
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        batch_size: Optional[int] = None,
    ):
        self.model_name = model_name or settings.embedding_model
        self.device = device or settings.embedding_device
        self.batch_size = batch_size or settings.embedding_batch_size
        self._model = None

    # ──────────────────────────────────────────────────────────────
    # MODEL LOADING (lazy)
    # ──────────────────────────────────────────────────────────────

    def load(self) -> "EmbeddingService":
        """Muat model secara eksplisit (untuk preloading di startup)."""
        _ = self._get_model()
        return self

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"[EMBEDDING] Memuat model: {self.model_name} (device={self.device})")
                self._model = SentenceTransformer(self.model_name, device=self.device)
                logger.info(
                    f"[EMBEDDING] Model siap — dimensi={self._get_dim(self._model)}"
                )
            except Exception as e:
                logger.error(f"[EMBEDDING] Gagal memuat model: {e}")
                raise
        return self._model

    @staticmethod
    def _get_dim(model) -> int:
        """Compat helper: get_embedding_dimension (baru) vs get_sentence_embedding_dimension (lama)."""
        if hasattr(model, "get_embedding_dimension"):
            return model.get_embedding_dimension()
        return model.get_sentence_embedding_dimension()

    @property
    def embedding_dim(self) -> int:
        """Dimensi vektor output model."""
        return self._get_dim(self._get_model())

    # ──────────────────────────────────────────────────────────────
    # EMBEDDING (sync)
    # ──────────────────────────────────────────────────────────────

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Embed list of texts secara sinkron.
        Returns list of float vectors (normalized, cosine-ready).
        """
        if not texts:
            return []

        model = self._get_model()
        show_progress = len(texts) > 20

        logger.debug(f"[EMBEDDING] Encoding {len(texts)} teks...")
        embeddings = model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=True,  # L2 normalize → cosine similarity = dot product
            convert_to_numpy=True,
        )
        return embeddings.tolist()

    def embed_text(self, text: str) -> list[float]:
        """Embed satu teks."""
        return self.embed_texts([text])[0]

    # ──────────────────────────────────────────────────────────────
    # EMBEDDING (async)
    # ──────────────────────────────────────────────────────────────

    async def embed_texts_async(self, texts: list[str]) -> list[list[float]]:
        """
        Embed list of texts secara asinkron.
        Menjalankan encode di thread pool agar tidak memblokir event loop.
        """
        if not texts:
            return []
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_texts, texts)

    async def embed_chunks(
        self,
        chunks: list[DocumentChunk],
        only_children: bool = False,
    ) -> list[DocumentChunk]:
        """
        Embed semua chunks dan isi field `.embedding` di setiap chunk.

        Args:
            chunks: List DocumentChunk yang akan di-embed.
            only_children: Jika True, hanya embed Ayat (L3) dan Pasal
                           tanpa parent (leaf chunks). Berguna untuk
                           menghemat ruang Qdrant — hanya child yang
                           di-index untuk vector search.

        Returns:
            List chunks yang sama dengan `.embedding` sudah terisi.
        """
        if not chunks:
            return chunks

        target_chunks = chunks
        if only_children:
            # Hanya chunk yang tidak punya parent_chunk_id (root) atau
            # chunk level 3 (Ayat) dan level 2 tanpa anak (Pasal leaf)
            target_chunks = [
                c for c in chunks
                if c.metadata.level_number >= 2
            ]

        if not target_chunks:
            return chunks

        logger.info(f"[EMBEDDING] Mulai embed {len(target_chunks)} chunk(s)...")
        texts = [c.content for c in target_chunks]
        embeddings = await self.embed_texts_async(texts)

        for chunk, emb in zip(target_chunks, embeddings):
            chunk.embedding = emb

        logger.info(
            f"[EMBEDDING] Selesai: {len(target_chunks)} chunks | "
            f"dim={len(embeddings[0]) if embeddings else 0}"
        )
        return chunks
