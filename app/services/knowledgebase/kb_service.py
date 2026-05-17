#kb_service.py

from typing import Dict, Optional
from app.core.qdrant import qdrant_db
from app.core.embeddings import embeddings
from app.services.prompting.prompt.repair_text import text_refiner
from .pdf_extractor import PDFExtractor
from .legal_parser import LegalParser
from .qdrant_storage import QdrantStorage

class KnowledgeBaseService:
    def __init__(self):
        self.extractor = PDFExtractor()
        self.parser = LegalParser()
        self.storage = QdrantStorage(qdrant_db.client, embeddings)

    async def create_knowledgebase(self, base_name: str, file_content: bytes) -> Dict:
        parent_col, child_col = f"{base_name}_parent", f"{base_name}_child"
        
        await self.storage.init_collections([parent_col, child_col])
        
        raw_text = self.extractor.extract_text(file_content)
        refinement = await text_refiner.repair_legal_text(raw_text)
        clean_text = refinement["repaired_text"]
        doc_structure = self.parser.parse_uu_structure(clean_text)
        
        doc_id = doc_structure["metadata"].get("uu_id", f"UU_{base_name}")
        
        await self.storage.store_parent_section(
            parent_col, child_col, doc_structure["pembukaan"], doc_id,
            doc_structure["metadata"], "pembukaan", "identitas",
            f"UU {doc_structure['metadata'].get('uu_number', 'N/A')}/{doc_structure['metadata'].get('tahun', 'N/A')}"
        )
        
        await self.storage.store_batang_tubuh(parent_col, child_col, doc_structure["pasal_list"], doc_id, doc_structure["metadata"])
        
        if doc_structure.get("penjelasan"):
            await self.storage.store_penjelasan(parent_col, child_col, doc_structure["penjelasan"], doc_id, doc_structure["metadata"])
            
        return {
            "status": "success", "document_id": doc_id,
            "total_pasal": len(doc_structure["pasal_list"]),
            "metadata": doc_structure["metadata"]
        }

    async def list_collections(self) -> list[str]:
        return await self.storage.list_collections()

    async def delete_knowledgebase(self, base_name: str) -> bool:
        return await self.storage.delete_knowledgebase(base_name)

    async def get_collection_stats(self, base_name: str) -> Dict:
        return await self.storage.get_stats(base_name)
    
    async def get_kb_info(self, base_name: str) -> Dict:
        return await self.storage.get_kb_info(base_name)
    
    async def search_knowledgebase(
        self,
        base_name: str,
        query: str,
        section_type: Optional[str] = None,
        pasal_type: Optional[str] = None,
        limit: int = 5
    ) -> Dict:
        return await self.storage.search_knowledgebase(
            base_name, query, section_type, pasal_type, limit
        )

# Singleton
kb_service = KnowledgeBaseService()