"""
Qdrant service moved into knowledgebase package.
"""

import logging
from typing import Optional, List, Dict, Any

from app.core.config import settings
from app.database.models.schemas import DocumentChunk

logger = logging.getLogger(__name__)


class QdrantService:
    def __init__(self):
        self._host = settings.qdrant_host
        self._port = settings.qdrant_port
        self._collection_parent = settings.embedding_collection_parent
        self._collection_child = settings.embedding_collection_child

    def _get_client(self):
        from qdrant_client import QdrantClient
        return QdrantClient(host=self._host, port=self._port, timeout=10)

    def health_check(self) -> dict:
        try:
            client = self._get_client()
            collections = client.get_collections()
            return {"status": "ok", "host": self._host, "port": self._port, "collections": len(collections.collections), "collection_names": [c.name for c in collections.collections]}
        except Exception as e:
            logger.warning(f"[QDRANT] Health check gagal: {e}")
            return {"status": "error", "detail": str(e), "host": self._host, "port": self._port}

    def list_knowledgebase_names(self) -> List[str]:
        """Return base knowledgebase names from collections ending with _parent."""
        client = self._get_client()
        collections = client.get_collections()
        return sorted({c.name.replace("_parent", "") for c in collections.collections if c.name.endswith("_parent")})

    # Other methods preserved (ensure_collection, upsert_chunks, search...) — omitted for brevity
