#kb_service.py

from typing import Dict, Optional
from app.core.qdrant import qdrant_db
from app.core.embeddings import embeddings
from app.services.prompting.prompt.repair_text import text_refiner
from .pdf_extractor import PDFExtractor
from .legal_parser import LegalParser
from .qdrant_storage import QdrantStorage
import re

class KnowledgeBaseService:
    def __init__(self):
        self.extractor = PDFExtractor()
        self.parser = LegalParser()
        self.storage = QdrantStorage(qdrant_db.client, embeddings)

    async def create_knowledgebase(self, base_name: str, file_content: bytes) -> Dict:

        parent_col = f"{base_name}_parent"
        child_col = f"{base_name}_child"

        await self.storage.init_collections([parent_col, child_col])
        
        # =====================================================
        # 1. Extract text dari PDF
        # =====================================================

        raw_text = self.extractor.extract_text(file_content)

        if not raw_text.strip():
            raise ValueError("File PDF tidak mengandung teks yang dapat dibaca.")
        
        # =====================================================
        # 2. CLEANING MANUAL (AMAN UNTUK UU)
        # =====================================================

        clean_text = raw_text

        #hapus karakter aneh
        clean_text = clean_text.replace("\x00", " ")  # null byte
    
        # normalize whitespace
        clean_text = " ".join(clean_text.split())

        #kembalikan line penting hukum
        clean_text = clean_text.replace("Pasal ", "\nPasal ")
        clean_text = clean_text.replace("BAB ", "\nBAB ")

        #rapikan newline berlebih
        clean_text = re.sub(r'\n{3,}', '\n\n', clean_text)

        # =====================================================
        # 3. OPTIONAL AI CLEANING (NON WAJIB)
        # =====================================================
        """
        AI cleaning DISARANKAN hanya untuk:
        - OCR rusak
        - typo ringan
        - bukan mengganti struktur hukum
        """

        USE_AI_REFINER = False

        if USE_AI_REFINER:
            try:
                refined = await text_refiner.refine_text(clean_text)

                if isinstance(refined, dict):
                    clean_text = refined.get("refined_text", clean_text)
            except Exception as e:
                print(f"AI Refiner gagal: {e}")

        # =====================================================
        # 4. Parsing Struktur UU
        # =====================================================
        
        doc_structure = self.parser.parse_uu_structure(clean_text)

        doc_id = doc_structure["metadata"].get("uu_id", f"UU_{base_name}")
        
        # =====================================================
        # 5. Simpan Pembukaan
        # =====================================================

        await self.storage.store_parent_section(
            parent_col, 
            child_col, 
            doc_structure["pembukaan"], 
            doc_id,
            doc_structure["metadata"], 
            "pembukaan", 
            "identitas",
            f"UU {doc_structure['metadata'].get('uu_number', 'N/A')}/{doc_structure['metadata'].get('tahun', 'N/A')}"
        )

        # =====================================================
        # 6. Simpan Batang Tubuh
        # =====================================================
        
        await self.storage.store_batang_tubuh(
            parent_col, 
            child_col, 
            doc_structure["pasal_list"], 
            doc_id, 
            doc_structure["metadata"]
        )
        
        # =====================================================
        # 7. Simpan Penjelasan
        # =====================================================

        if doc_structure.get("penjelasan"):
            await self.storage.store_penjelasan(
                parent_col, 
                child_col, 
                doc_structure["penjelasan"], 
                doc_id, 
                doc_structure["metadata"]
            )
        # =====================================================
        # 8. Return
        # =====================================================     
        #        
        return {
            "status": "success", 
            "document_id": doc_id,
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