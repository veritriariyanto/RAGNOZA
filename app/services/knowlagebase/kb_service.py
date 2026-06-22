#kb_service.py

import asyncio
from typing import Dict, Optional, List
from app.core.embeddings import embeddings
from .cleaning_service import CleaningService
from .chunking_service import ChunkingService
from .qdrant_service import QdrantService

class KnowledgeBaseService:
    def __init__(self):
        self.cleaning_service = CleaningService()
        self.chunking_service = ChunkingService()
        self.qdrant_service = QdrantService()

    async def create_knowledgebase(self, base_name: str, file_content: bytes) -> Dict:
        """
        Membuat KB baru dari file PDF menggunakan pipeline baru:
        Cleaning (PyMuPDF + regex) -> Chunking (Parent-Child) -> Embedding -> Qdrant Store.
        """
        # 1. Cleaning (jalankan di thread pool karena CPU-bound)
        cleaning_result = await asyncio.to_thread(
            self.cleaning_service.clean_from_bytes,
            file_content,
            f"{base_name}.pdf"
        )
        doc_id = cleaning_result.document_id

        # 2. Chunking
        chunking_result = await self.chunking_service.chunk(cleaning_result)
        raw_chunks = chunking_result.__dict__.get("raw_chunks", [])

        # 3. Store to Qdrant (dengan batching embedding otomatis)
        store_result = await self.qdrant_service.store_chunks(
            raw_chunks=raw_chunks,
            base_name=base_name,
            document_id=doc_id,
            embed_fn=embeddings.embed_documents
        )

        return {
            "status": "success",
            "document_id": doc_id,
            "total_pasal": len(cleaning_result.__dict__.get("pasal_data", [])),
            "metadata": cleaning_result.metadata,
            "qdrant_stats": store_result
        }

    async def list_collections(self) -> List[str]:
        return await self.qdrant_service.list_collections()

    async def delete_knowledgebase(self, base_name: str) -> bool:
        return await self.qdrant_service.delete_knowledgebase(base_name)

    async def get_collection_stats(self, base_name: str) -> Dict:
        return await self.qdrant_service.get_stats(base_name)

    async def get_kb_info(self, base_name: str) -> Dict:
        return await self.qdrant_service.get_kb_info(base_name)

    async def search_knowledgebase(
        self,
        base_name: str,
        query: str,
        section_type: Optional[str] = None,
        pasal_type: Optional[str] = None,
        limit: int = 5
    ) -> Dict:
        return await self.qdrant_service.search_knowledgebase(
            base_name=base_name,
            query=query,
            section_type=section_type,
            pasal_type=pasal_type,
            limit=limit
        )

# Singleton
kb_service = KnowledgeBaseService()