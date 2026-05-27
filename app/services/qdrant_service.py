"""
app/services/qdrant_service.py
================================
Wrapper service untuk Qdrant Vector Database.

Mendukung arsitektur Parent-Child Dual-Collection:
- Parent collection (`embedding_collection_parent`): Menyimpan chunk berukuran besar
  (BAB, Pasal utuh) sebagai unit pembawa konteks penuh.
- Child collection (`embedding_collection_child`): Menyimpan chunk berukuran kecil
  (Ayat, Pasal tanpa ayat) yang di-embed untuk kemiripan semantik (vector search).
"""

import logging
from typing import Optional, List, Dict, Any

# pyrefly: ignore [missing-import]
from app.config import settings
from app.database.models.schemas import DocumentChunk

logger = logging.getLogger(__name__)


class QdrantService:
    """Wrapper Qdrant client untuk indexing dan dual-collection retrieval chunks UU."""

    def __init__(self):
        self._host = settings.qdrant_host
        self._port = settings.qdrant_port
        self._collection_parent = settings.embedding_collection_parent
        self._collection_child = settings.embedding_collection_child

    def _get_client(self):
        from qdrant_client import QdrantClient  # pyrefly: ignore [missing-import]
        return QdrantClient(host=self._host, port=self._port, timeout=10)

    # ──────────────────────────────────────────────────────────────
    # HEALTH CHECK & COLLECTIONS MANAGEMENT
    # ──────────────────────────────────────────────────────────────

    def health_check(self) -> dict:
        """Cek koneksi dan status collection di Qdrant."""
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

    def get_collections_detailed(self) -> List[Dict[str, Any]]:
        """Ambil info detail untuk semua collection di Qdrant."""
        try:
            client = self._get_client()
            collections = client.get_collections()
            detailed = []
            for col in collections.collections:
                try:
                    info = client.get_collection(col.name)
                    vectors_config = info.config.params.vectors
                    vector_size = None
                    distance = None
                    if hasattr(vectors_config, 'size'):
                        vector_size = vectors_config.size
                        distance = str(vectors_config.distance)
                    elif isinstance(vectors_config, dict):
                        if 'size' in vectors_config:
                            vector_size = vectors_config['size']
                            distance = str(vectors_config.get('distance'))
                        elif len(vectors_config) > 0:
                            first_val = list(vectors_config.values())[0]
                            vector_size = getattr(first_val, 'size', None) or (first_val.get('size') if isinstance(first_val, dict) else None)
                            distance = str(getattr(first_val, 'distance', None) or (first_val.get('distance') if isinstance(first_val, dict) else None))
                    
                    detailed.append({
                        "name": col.name,
                        "status": str(info.status),
                        "points_count": info.points_count,
                        "vectors_count": getattr(info, 'vectors_count', None),
                        "vector_size": vector_size,
                        "distance": distance,
                    })
                except Exception as e:
                    detailed.append({
                        "name": col.name,
                        "status": "error",
                        "error": str(e)
                    })
            return detailed
        except Exception as e:
            logger.error(f"[QDRANT] Gagal mengambil detail collections: {e}")
            return []

    def ensure_collection(self, collection_name: str, vector_size: int = 384) -> bool:
        """Pastikan collection ada di Qdrant. Jika belum, buat otomatis."""
        from qdrant_client.models import VectorParams, Distance  # pyrefly: ignore [missing-import]

        client = self._get_client()
        try:
            client.get_collection(collection_name)
            return True
        except Exception:
            pass

        try:
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"[QDRANT] Collection '{collection_name}' berhasil dibuat (dim={vector_size})")
            return True
        except Exception as e:
            logger.error(f"[QDRANT] Gagal membuat collection '{collection_name}': {e}")
            return False

    def delete_collection(self, collection_name: str) -> bool:
        """Hapus collection dari Qdrant."""
        try:
            client = self._get_client()
            client.delete_collection(collection_name)
            logger.info(f"[QDRANT] Collection '{collection_name}' berhasil dihapus")
            return True
        except Exception as e:
            logger.error(f"[QDRANT] Gagal menghapus collection '{collection_name}': {e}")
            return False

    # ──────────────────────────────────────────────────────────────
    # UPSERT CHUNKS
    # ──────────────────────────────────────────────────────────────

    def upsert_chunks(
        self,
        chunks: List[DocumentChunk],
        collection_name: Optional[str] = None,
        only_embedded: bool = True,
    ) -> dict:
        """
        Upsert chunks ke Qdrant.

        Jika `collection_name` di-pass (tidak None), semua chunks akan dipaksa masuk ke sana.
        Jika `collection_name` adalah None (default), chunks akan dipilah secara otomatis:
        - Parent chunks (`is_parent=True`) masuk ke `embedding_collection_parent`.
        - Child chunks (`is_parent=False`) masuk ke `embedding_collection_child`.
        """
        # Filter chunks yang memiliki embedding
        to_upsert = [c for c in chunks if (not only_embedded or c.embedding is not None)]
        if not to_upsert:
            logger.warning("[QDRANT] Tidak ada chunk dengan embedding untuk di-upsert")
            return {"upserted": 0, "skipped": len(chunks)}

        # Jika nama collection di-override oleh parameter call
        if collection_name:
            result = self._upsert_to_single_collection(to_upsert, collection_name)
            return {
                "upserted": result,
                "skipped": len(chunks) - result,
                "collection_mode": "single",
                "collection": collection_name,
            }

        # Pisahkan parent vs child
        parent_chunks = [c for c in to_upsert if c.metadata.is_parent]
        child_chunks = [c for c in to_upsert if not c.metadata.is_parent]

        upserted_parent = 0
        upserted_child = 0

        if parent_chunks:
            upserted_parent = self._upsert_to_single_collection(parent_chunks, self._collection_parent)
        if child_chunks:
            upserted_child = self._upsert_to_single_collection(child_chunks, self._collection_child)

        total_upserted = upserted_parent + upserted_child
        skipped = len(chunks) - total_upserted

        logger.info(
            f"[QDRANT] Upsert selesai (Dual-Collection): "
            f"Parent={upserted_parent} → '{self._collection_parent}', "
            f"Child={upserted_child} → '{self._collection_child}' (skipped={skipped})"
        )

        return {
            "upserted": total_upserted,
            "skipped": skipped,
            "collection_mode": "dual",
            "parent_collection": self._collection_parent,
            "child_collection": self._collection_child,
            "parent_count": upserted_parent,
            "child_count": upserted_child,
        }

    def _upsert_to_single_collection(self, chunks: List[DocumentChunk], collection_name: str) -> int:
        """Helper internal untuk upsert list chunk ke suatu collection tertentu."""
        from qdrant_client.models import PointStruct  # pyrefly: ignore [missing-import]

        vector_size = len(chunks[0].embedding)
        self.ensure_collection(collection_name, vector_size=vector_size)

        points: List[PointStruct] = []
        for chunk in chunks:
            payload = chunk.metadata.model_dump()
            payload["chunk_id"] = chunk.chunk_id
            payload["content"] = chunk.content

            points.append(
                PointStruct(
                    id=chunk.chunk_id,
                    vector=chunk.embedding,
                    payload=payload,
                )
            )

        client = self._get_client()
        batch_size = 100
        total_upserted = 0
        
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            client.upsert(collection_name=collection_name, points=batch)
            total_upserted += len(batch)
            
        return total_upserted

    # ──────────────────────────────────────────────────────────────
    # SEARCH
    # ──────────────────────────────────────────────────────────────

    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        collection_name: Optional[str] = None,
        score_threshold: float = 0.3,
        filter_level: Optional[int] = None,
    ) -> List[dict]:
        """
        Similarity search. Lakukan search default pada child collection
        karena child collection menyimpan ayat-ayat yang sangat granular.
        """
        from qdrant_client.models import Filter, FieldCondition, MatchValue  # pyrefly: ignore [missing-import]

        # Mode default: cari di child collection
        name = collection_name or self._collection_child
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
            results = client.query_points(
                collection_name=name,
                query=query_vector,
                limit=top_k,
                score_threshold=score_threshold,
                query_filter=query_filter,
                with_payload=True,
            ).points
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
            logger.error(f"[QDRANT] Search gagal pada collection '{name}': {e}")
            return []

    # ──────────────────────────────────────────────────────────────
    # RETRIEVAL (GET CHUNK BY ID & PARENT FETCH)
    # ──────────────────────────────────────────────────────────────

    def get_chunk_by_id(
        self,
        chunk_id: str,
        collection_name: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Ambil satu chunk berdasarkan ID.
        Jika `collection_name` None, cari di parent collection terlebih dahulu,
        kemudian fallback ke child collection jika tidak ditemukan.
        """
        client = self._get_client()

        # Tentukan urutan pencarian collection
        collections_to_search = []
        if collection_name:
            collections_to_search = [collection_name]
        else:
            collections_to_search = [self._collection_parent, self._collection_child]

        for col in collections_to_search:
            try:
                results = client.retrieve(
                    collection_name=col,
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
            except Exception as e:
                logger.debug(f"[QDRANT] Retrieve ID '{chunk_id}' gagal pada '{col}': {e}")
                continue
                
        return None

    def fetch_parent(
        self,
        child_chunk_id: str,
        collection_name: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Ambil parent chunk utuh berdasarkan id child chunk.
        Secara default mencari ID parent_chunk_id di parent collection.
        """
        child = self.get_chunk_by_id(child_chunk_id, collection_name)
        if not child:
            return None

        parent_id = child.get("parent_chunk_id")
        if not parent_id:
            return None

        # Fetch parent menggunakan get_chunk_by_id (akan mencari di parent collection secara default)
        return self.get_chunk_by_id(parent_id, collection_name)
