import logging
from typing import Optional
from app.services.prompting.audio.stt_service import STTService
from app.services.prompting.prompt.repair_text import TextRefinerService
from app.services.knowledgebase.qdrant_storage import QdrantStorage
from app.services.prompting.prompt.generate_content_service import MaterialGeneratorService
from app.schemas.prompting.generate_content import MaterialRequest
from app.schemas.prompting.integration import RAGIntegrationResponse

logger = logging.getLogger(__name__)

class RAGIntegrationService:
    def __init__(
        self, 
        stt_service: STTService, 
        text_service: TextRefinerService, 
        vector_service: QdrantStorage,
        material_service: MaterialGeneratorService # Tambahkan ini
    ):
        self.stt_service = stt_service
        self.text_service = text_service
        self.vector_service = vector_service
        self.material_service = material_service

    async def process_audio_to_material(
        self, 
        audio_bytes: bytes, 
        filename: str, 
        knowledge_base: str = "uud_1945",
        provider: str = "whisper",
        style: str = "formal"
    ) -> RAGIntegrationResponse:
        """
        Alur Terintegrasi Penuh: STT -> Repair -> Search -> Generate Material
        """
        try:
            # Tahap 1: Transkripsi
            raw_transcribe = await self.stt_service.transcribe(
                audio_bytes=audio_bytes, 
                provider=provider, 
                filename=filename
            )

            # Tahap 2: Repair Text & Generate Search Query
            refinement = await self.text_service.repair_legal_text(raw_transcribe)
            repaired_text = refinement["repaired_text"]
            search_query = refinement["search_query"]

            # Tahap 3: Semantic Search ke Qdrant (Child-Parent)
            kb_results = await self.vector_service.search_knowledgebase(
                base_name=knowledge_base,
                query=search_query,
                limit=3
            )

            # Tahap 4: Ekstraksi Konteks
            contexts = []
            for res in kb_results.get("results", []):
                parent_content = res.get("parent", {}).get("content")
                if parent_content:
                    contexts.append(parent_content)
            
            combined_context = "\n\n".join(contexts)

            # Tahap 5: GENERATE MATERIAL (Langkah Final)
            # Menggunakan context dari Qdrant + instruksi asli pengguna
            final_material = None
            if len(contexts) > 0:
                material_payload = MaterialRequest(
                    context_text=f"KONTEKS HUKUM:\n{combined_context}\n\nFAKTA/TRANSKRIPSI:\n{repaired_text}",
                    style=style
                )
                final_material = await self.material_service.generate_legal_material(material_payload)

            return RAGIntegrationResponse(
                raw_transcribe=raw_transcribe,
                final_repaired_text=repaired_text,
                search_query_used=search_query,
                retrieved_context=combined_context,
                source_details=kb_results.get("results", []),
                final_material=final_material,
                has_context=len(contexts) > 0
            )

        except Exception as e:
            logger.error(f"[Critical Error] RAGIntegration: {str(e)}")
            raise e

    