"""
Embedding service (moved into knowledgebase package).
"""

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

from app.config import settings
from app.database.models.schemas import DocumentChunk


class EmbeddingService:
    def __init__(self, model_name: Optional[str] = None, device: Optional[str] = None, batch_size: Optional[int] = None):
        self.model_name = model_name or settings.embedding_model
        self.device = device or settings.embedding_device
        self.batch_size = batch_size or settings.embedding_batch_size
        self._model = None

    def load(self) -> "EmbeddingService":
        _ = self._get_model()
        return self

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"[EMBEDDING] Memuat model: {self.model_name} (device={self.device})")
                self._model = SentenceTransformer(self.model_name, device=self.device)
            except Exception as e:
                logger.error(f"[EMBEDDING] Gagal memuat model: {e}")
                raise
        return self._model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._get_model()
        embeddings = model.encode(texts, batch_size=self.batch_size, show_progress_bar=False, normalize_embeddings=True, convert_to_numpy=True)
        return embeddings.tolist()

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    async def embed_texts_async(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_texts, texts)

    async def embed_chunks(self, chunks: list[DocumentChunk], only_children: bool = False) -> list[DocumentChunk]:
        if not chunks:
            return chunks
        target_chunks = chunks
        if only_children:
            target_chunks = [c for c in chunks if c.metadata.level_number >= 2]
        texts = [c.content for c in target_chunks]
        embeddings = await self.embed_texts_async(texts)
        for chunk, emb in zip(target_chunks, embeddings):
            chunk.embedding = emb
        return chunks
