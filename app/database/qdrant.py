from qdrant_client import QdrantClient
import os

def get_qdrant_client():
    return QdrantClient(
        url=os.getenv("QDRANT_HOST"),
        port=int(os.getenv("QDRANT_PORT", 6333))
    )