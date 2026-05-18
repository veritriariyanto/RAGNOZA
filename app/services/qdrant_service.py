"""
app/services/qdrant_service.py
================================
Wrapper service around the Qdrant vector database client.

Menyediakan:
- health_check()       → cek koneksi Qdrant
- ensure_collection()  → buat collection jika belum ada
- upsert_chunks()      → simpan chunks yang sudah di-embed
- search()             → similarity search berdasarkan query vector
- get_chunk()          → ambil chunk by ID
- fetch_parent()       → ambil parent chunk dari child chunk_id
"""

import logging
from typing import Optional

from app.config import settings
from app.models.schemas import DocumentChunk

logger = logging.getLogger(__name__)


class QdrantService:
    """Wrapper Qdrant client untuk indexing dan retrieval chunks UU."""

    def __init__(self):
        self._host = settings.qdrant_host
        self._port = settings.qdrant_port
        self._collection_parent = settings.embedding_collection_parent
        self._collection_child = settings.embedding_collection_child

    def _get_client(self):
        from qdrant_client import QdrantClient
        return QdrantClient(host=self._host, port=self._port, timeout=10)

    # ──────────────────────────────────────────────────────────────
    # HEALTH CHECK
    # ──────────────────────────────────────────────────────────────

    def health_check(self) -> dict:
        """Ping Qdrant dan return status dict."""
        try:
            client = self._get_client()
            collections = client.get_collections()
            return {
                "status": "ok",
                "host": self._host,
                "port": self._port,
                "collections": len(collections.collections),
                "collection_names": [c.name for c in collections.collections],
            }
        except Exception as e:
            logger.warning(f"[QDRANT] Health check gagal: {e}")
            return {
                "status": "error",
                "detail": str(e),
                "host": self._host,
                "port": self._port,
            }

    # ──────────────────────────────────────────────────────────────
    # COLLECTION MANAGEMENT
    # ──────────────────────────────────────────────────────────────

    def ensure_collection(
        self,
        collection_name: Optional[str] = None,
        vector_size: int = 384,
    ) -> bool:
        """
        Pastikan collection ada di Qdrant.
        Jika belum ada → buat otomatis dengan COSINE distance.

        Returns True jika collection sudah/baru dibuat, False jika error.
        """
        from qdrant_client.models import VectorParams, Distance

        name = collection_name or self._collection
        client = self._get_client()

        try:
            client.get_collection(name)
            logger.debug(f"[QDRANT] Collection '{name}' sudah ada")
            return True
        except Exception:
            # Collection belum ada → buat baru
            pass

        try:
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"[QDRANT] Collection '{name}' dibuat (dim={vector_size}, COSINE)")
            return True
        except Exception as e:
            logger.error(f"[QDRANT] Gagal membuat collection '{name}': {e}")
            return False

    def delete_collection(self, collection_name: Optional[str] = None) -> bool:
        """Hapus collection (untuk reset index)."""
        name = collection_name or self._collection
        try:
            client = self._get_client()
            client.delete_collection(name)
            logger.info(f"[QDRANT] Collection '{name}' dihapus")
            return True
        except Exception as e:
            logger.error(f"[QDRANT] Gagal hapus collection '{name}': {e}")
            return False

    # ──────────────────────────────────────────────────────────────
    # UPSERT CHUNKS
    # ──────────────────────────────────────────────────────────────

    def upsert_chunks(
        self,
        chunks: list[DocumentChunk],
        collection_name: Optional[str] = None,
        only_embedded: bool = True,
    ) -> dict:
        """
        Upsert chunks yang sudah memiliki embedding ke Qdrant.

        Args:
            chunks:          List DocumentChunk (harus sudah ada .embedding)
            collection_name: Override collection name (default dari settings)
            only_embedded:   Jika True, skip chunk yang belum punya embedding

        Returns:
            Dict dengan statistik upsert
        """
        from qdrant_client.models import PointStruct

        name = collection_name or self._collection

        # Filter hanya chunk yang punya embedding
        to_upsert = [
            c for c in chunks
            if (not only_embedded or c.embedding is not None)
        ]

        if not to_upsert:
            logger.warning("[QDRANT] Tidak ada chunk dengan embedding untuk di-upsert")
            return {"upserted": 0, "skipped": len(chunks), "collection": name}

        # Pastikan collection ada (auto-create dengan dimensi dari chunk pertama)
        vector_size = len(to_upsert[0].embedding)
        self.ensure_collection(name, vector_size=vector_size)

        # Bangun PointStruct list
        points: list[PointStruct] = []
        for chunk in to_upsert:
            payload = chunk.metadata.model_dump()
            # Tambahkan field tambahan ke payload untuk kemudahan retrieval
            payload["chunk_id"] = chunk.chunk_id
            payload["content"] = chunk.content
            payload["is_parent"] = chunk.metadata.level_number < 3 and bool(
                chunk.metadata.ayat_number is None
                and chunk.metadata.level_number < 2
            )

            points.append(
                PointStruct(
                    id=chunk.chunk_id,
                    vector=chunk.embedding,
                    payload=payload,
                )
            )

        client = self._get_client()
        # Upsert dalam batch agar tidak timeout untuk dokumen besar
        batch_size = 100
        total_upserted = 0
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            client.upsert(collection_name=name, points=batch)
            total_upserted += len(batch)
            logger.debug(f"[QDRANT] Upserted {total_upserted}/{len(points)} points")

        skipped = len(chunks) - total_upserted
        logger.info(
            f"[QDRANT] Upsert selesai: {total_upserted} points → collection '{name}' "
            f"(skipped={skipped})"
        )
        return {
            "upserted": total_upserted,
            "skipped": skipped,
            "collection": name,
            "vector_size": vector_size,
        }

    # ──────────────────────────────────────────────────────────────
    # SEARCH
    # ──────────────────────────────────────────────────────────────

    def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        collection_name: Optional[str] = None,
        score_threshold: float = 0.3,
        filter_level: Optional[int] = None,
    ) -> list[dict]:
        """
        Similarity search berdasarkan query vector.

        Args:
            query_vector:     Vector query dari embedding model
            top_k:            Jumlah hasil teratas
            collection_name:  Override collection (default dari settings)
            score_threshold:  Minimum similarity score (0-1)
            filter_level:     Filter berdasarkan level_number (None = semua)

        Returns:
            List dict berisi chunk_id, score, dan payload
        """
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        name = collection_name or self._collection
        client = self._get_client()

        query_filter = None
        if filter_level is not None:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="level_number",
                        match=MatchValue(value=filter_level),
                    )
                ]
            )

        try:
            results = client.search(
                collection_name=name,
                query_vector=query_vector,
                limit=top_k,
                score_threshold=score_threshold,
                query_filter=query_filter,
                with_payload=True,
            )
            return [
                {
                    "chunk_id": str(hit.id),
                    "score": round(hit.score, 4),
                    "content": hit.payload.get("content", ""),
                    "level_number": hit.payload.get("level_number"),
                    "hierarchy_level": hit.payload.get("hierarchy_level"),
                    "document_title": hit.payload.get("document_title"),
                    "bab_title": hit.payload.get("bab_title"),
                    "pasal_title": hit.payload.get("pasal_title"),
                    "ayat_number": hit.payload.get("ayat_number"),
                    "parent_chunk_id": hit.payload.get("parent_chunk_id"),
                    "source_filename": hit.payload.get("source_filename"),
                }
                for hit in results
            ]
        except Exception as e:
            logger.error(f"[QDRANT] Search gagal: {e}")
            return []

    def get_chunk_by_id(
        self,
        chunk_id: str,
        collection_name: Optional[str] = None,
    ) -> Optional[dict]:
        """Ambil satu chunk berdasarkan ID (untuk fetch parent chunk)."""
        name = collection_name or self._collection
        client = self._get_client()

        try:
            results = client.retrieve(
                collection_name=name,
                ids=[chunk_id],
                with_payload=True,
            )
            if results:
                point = results[0]
                payload = point.payload or {}
                return {
                    "chunk_id": str(point.id),
                    "content": payload.get("content", ""),
                    **{k: v for k, v in payload.items() if k != "content"},
                }
            return None
        except Exception as e:
            logger.error(f"[QDRANT] get_chunk_by_id gagal: {e}")
            return None

    def fetch_parent(
        self,
        child_chunk_id: str,
        collection_name: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Ambil parent chunk dari sebuah child chunk.
        Digunakan dalam RAG untuk mendapatkan konteks lebih luas.
        """
        child = self.get_chunk_by_id(child_chunk_id, collection_name)
        if not child:
            return None

        parent_id = child.get("parent_chunk_id")
        if not parent_id:
            return None

        return self.get_chunk_by_id(parent_id, collection_name)
