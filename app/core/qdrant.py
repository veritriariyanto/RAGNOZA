from qdrant_client import QdrantClient
from qdrant_client.http import models
import os
from dotenv import load_dotenv

load_dotenv()

class QdrantManager:
    def __init__(self):
        self.client = QdrantClient(
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", 6333))
        )
        # Hapus self.collection_name statis agar tidak membingungkan

    def init_collection(self, collection_name: str, vector_size: int = 384):
        """
        Memastikan koleksi spesifik siap digunakan.
        Jika belum ada, koleksi akan dibuat otomatis.
        """
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == collection_name for c in collections)
            
            if not exists:
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(
                        size=vector_size, 
                        distance=models.Distance.COSINE
                    ),
                )
                print(f"✅ Koleksi '{collection_name}' berhasil dibuat.")
            else:
                print(f"ℹ️ Koleksi '{collection_name}' sudah tersedia.")
        except Exception as e:
            print(f"❌ Gagal inisialisasi Qdrant untuk koleksi {collection_name}: {e}")

    def get_all_collections(self):
        """Helper untuk mengambil daftar koleksi yang ada (untuk dropdown di frontend)"""
        try:
            collections = self.client.get_collections().collections
            return [c.name for c in collections]
        except Exception as e:
            print(f"❌ Gagal mengambil daftar koleksi: {e}")
            return []

# Inisialisasi Instance
qdrant_db = QdrantManager()