# qdrant.py

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
import os
from dotenv import load_dotenv

load_dotenv()

class QdrantManager:
    def __init__(self):
        self._client = None

    @property
    def client(self) -> AsyncQdrantClient:
        if self._client is None:
            self._client = AsyncQdrantClient(
                host=os.getenv("QDRANT_HOST", "localhost"),
                port=int(os.getenv("QDRANT_PORT", 6333)),
                timeout=30
            )
        return self._client

    async def init_collection(self, collection_name: str, vector_size: int = 384):
        collections = await self.client.get_collections()
        existing = {c.name for c in collections.collections}
        
        if collection_name not in existing:
            await self.client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE
                ),
                optimizers_config=models.OptimizersConfigDiff(
                    indexing_threshold=1000
                )
            )
            print(f"✅ Koleksi '{collection_name}' dibuat.")
        else:
            print(f"ℹ️ Koleksi '{collection_name}' sudah ada.")

    async def get_all_collections(self) -> list[str]:
        try:
            collections = await self.client.get_collections()
            return [c.name for c in collections.collections]
        except Exception as e:
            print(f"❌ Gagal list koleksi: {e}")
            return []

    async def health_check(self) -> bool:
        try:
            await self.client.get_collections()
            return True
        except Exception:
            return False

# Inisialisasi
qdrant_db = QdrantManager()