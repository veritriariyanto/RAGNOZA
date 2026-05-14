# app/services/prompting/integration/rag_integration_service.py

from typing import Dict, Any, Optional
from app.services.prompting.audio.stt_service import STTService
from app.services.prompting.prompt.repair_text import TextRefinerService
from app.services.knowledgebase.qdrant_storage import QdrantStorage

class RAGIntegrationService:
    def __init__(
        self, 
        stt_service: STTService, 
        text_service: TextRefinerService, 
        vector_service: QdrantStorage
    ):
        self.stt_service = stt_service
        self.text_service = text_service
        self.vector_service = vector_service

    async def process_audio_to_knowledge(
        self, 
        audio_bytes: bytes, 
        filename: str, 
        knowledge_base: str = "uud_1945",
        provider: str = "whisper"
    ) -> Dict[str, Any]:
        """
        Alur Terintegrasi:
        1. Transcribe (STT)
        2. Repair & Extract Query (LLM)
        3. Search Knowledge Base (Qdrant Child-Parent)
        """
        try:
            # Tahap 1: Transkripsi (Sesuai alur 'transcribe audio' di BPMN)
            raw_transcribe = await self.stt_service.transcribe(
                audio_bytes=audio_bytes, 
                provider=provider, 
                filename=filename
            )

            # Tahap 2: Repair Text & Generate Search Query (Sesuai 'repair text' di BPMN)
            # Mengembalikan {"repaired_text": "...", "search_query": "..."}
            refinement = await self.text_service.repair_legal_text(raw_transcribe)
            
            repaired_text = refinement["repaired_text"]
            search_query = refinement["search_query"]

            # Tahap 3: Semantic Search ke Qdrant (Sesuai 'query ke vektor database' di BPMN)
            # Menggunakan Child-Parent Retrieval yang sudah kamu buat
            kb_results = await self.vector_service.search_knowledgebase(
                base_name=knowledge_base,
                query=search_query,
                limit=3 # Ambil 3 konteks terbaik
            )

            # Tahap 4: Konstruksi Output Final (Sesuai 'gabungkan dengan transcribe' di BPMN)
            # Kita gabungkan konteks untuk persiapan "Generate Konten"
            contexts = []
            for res in kb_results.get("results", []):
                parent_content = res["parent"].get("content")
                if parent_content:
                    contexts.append(parent_content)

            combined_context = "\n\n".join(contexts)

            return {
                "raw_transcribe": raw_transcribe,
                "final_repaired_text": repaired_text,
                "search_query_used": search_query,
                "retrieved_context": combined_context,
                "source_details": kb_results.get("results", []),
                "has_context": len(contexts) > 0
            }

        except Exception as e:
            print(f"[Critical Error] RAGIntegration: {str(e)}")
            raise e