"""
rag_integration_service.py  (updated)

Perubahan dari versi lama:
- Evaluasi RAGAS dipindah ke BackgroundTask → tidak blocking response user
- Menggunakan EvaluationService (bukan RagasService mentah) → hasil lebih konsisten
- Menggunakan auto_evaluation_hook → ground truth otomatis dari context
- Hasil evaluasi di-log dengan format terstruktur (tidak hanya print)
- BackgroundTasks diteruskan dari router agar FastAPI bisa manage lifecycle-nya
"""

import logging
from typing import Optional

from fastapi import BackgroundTasks

from app.services.prompting.audio.stt_service import STTService
from app.services.prompting.prompt.repair_text import TextRefinerService
from app.services.knowlagebase.qdrant_storage import QdrantStorage
from app.services.prompting.prompt.generate_content_service import MaterialGeneratorService
from app.schemas.prompting.generate_content import MaterialRequest
from app.schemas.prompting.integration import RAGIntegrationResponse

from sqlalchemy.orm import Session
from app.services.evaluation.history.rag_history_service import RAGHistoryService
from app.services.evaluation.formatter import material_to_text
from app.services.evaluation.auto_evaluation_hook import trigger_auto_evaluation

logger = logging.getLogger(__name__)


class RAGIntegrationService:
    def __init__(
        self,
        stt_service: STTService,
        text_service: TextRefinerService,
        vector_service: QdrantStorage,
        material_service: MaterialGeneratorService,
        db: Session,
    ):
        self.db = db
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
        style: str = "formal",
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> RAGIntegrationResponse:
        """
        Alur Terintegrasi Penuh: STT → Repair → Search → Generate Material

        Args:
            audio_bytes       : Raw bytes dari file audio user
            filename          : Nama file audio (untuk logging)
            knowledge_base    : Nama collection Qdrant yang dipakai
            provider          : Provider STT (whisper / elevenlabs)
            style             : Gaya penulisan material (formal/casual/academic)
            background_tasks  : FastAPI BackgroundTasks — jika diisi, evaluasi RAGAS
                                dijalankan di background (tidak blocking response).
                                Jika None, evaluasi dilewati.

        Returns:
            RAGIntegrationResponse — hasil pipeline RAG lengkap
        """
        try:
            # ── Tahap 1: Transkripsi ──────────────────────────────────────────
            raw_transcribe = await self.stt_service.transcribe(
                audio_bytes=audio_bytes,
                provider=provider,
                filename=filename,
            )

            # ── Tahap 2: Repair Text & Generate Search Query ──────────────────
            refinement = await self.text_service.repair_legal_text(raw_transcribe)
            repaired_text = refinement["repaired_text"]
            search_query = refinement["search_query"]

            # ── Tahap 3: Semantic Search ke Qdrant (Child-Parent) ─────────────
            kb_results = await self.vector_service.search_knowledgebase(
                base_name=knowledge_base,
                query=search_query,
                limit=3,
            )

            # rag_integration_service.py — Tahap 4, GANTI SELURUH BLOK INI:

            # ── Tahap 4: Ekstraksi Konteks ────────────────────────────────────────
            contexts = []
            for res in kb_results.get("results", []):
                # Coba parent dulu (lebih lengkap)
                parent_content = res.get("parent", {}).get("content")
                if parent_content:
                    contexts.append(parent_content)
                    continue
                
                # Fallback ke child content jika parent kosong
                child_content = res.get("child", {}).get("content")
                if child_content:
                    contexts.append(child_content)

            combined_context = "\n\n".join(contexts)

            # Debug sementara
            print(f"[SERVICE DEBUG] contexts count: {len(contexts)}")
            print(f"[SERVICE DEBUG] combined_context length: {len(combined_context)}")
            print(f"[SERVICE DEBUG] sample: {combined_context[:200]}")

            # ── Tahap 5: Generate Material ────────────────────────────────────
            final_material = None
            fallback_message = None

            if contexts:
                material_payload = MaterialRequest(
                    context_text=(
                        f"KONTEKS HUKUM:\n{combined_context}"
                        f"\n\nFAKTA/TRANSKRIPSI:\n{repaired_text}"
                    ),
                    user_scenario=repaired_text,
                )
                final_material = await self.material_service.generate_legal_material(
                    material_payload
                )

                # Konversi material ke teks untuk evaluasi
                answer_text = material_to_text(final_material)

                # ── Tahap 6: Simpan History ───────────────────────────────────
                RAGHistoryService.save_history(
                    db=self.db,
                    knowledge_base=knowledge_base,
                    provider=provider,
                    raw_transcribe=raw_transcribe,
                    repaired_text=repaired_text,
                    search_query=search_query,
                    retrieved_context=combined_context,
                    final_material=final_material,
                )

                # ── Tahap 7: Evaluasi RAGAS (Background — tidak blocking) ─────
                #
                # Jika background_tasks tersedia (diteruskan dari router),
                # evaluasi dijalankan SETELAH response dikirim ke user.
                #
                # ground_truth = None → auto_evaluation_hook akan pakai
                # context pertama sebagai proxy ground truth secara otomatis.
                if background_tasks is not None:
                    background_tasks.add_task(
                        trigger_auto_evaluation,
                        question=repaired_text,
                        context=combined_context,
                        answer=answer_text,
                        ground_truth=None,          # proxy otomatis dari context
                        source_label="audio_rag",
                    )
                    logger.info(
                        "[RAGIntegration] Evaluasi RAGAS dijadwalkan di background "
                        "untuk query: %s...",
                        repaired_text[:60],
                    )
                else:
                    logger.debug(
                        "[RAGIntegration] background_tasks tidak tersedia — "
                        "evaluasi RAGAS dilewati."
                    )

            else:
                fallback_message = (
                    "Maaf, jawaban tidak dapat dibuat karena tidak ada "
                    "referensi hukum yang cocok."
                )

            return RAGIntegrationResponse(
                raw_transcribe=raw_transcribe,
                final_repaired_text=repaired_text,
                user_scenario=repaired_text,
                search_query_used=search_query,
                retrieved_context=combined_context,
                source_details=kb_results.get("results", []),
                final_material=final_material,
                fallback_message=fallback_message,
                has_context=len(contexts) > 0,
            )

        except Exception as exc:
            logger.error("[RAGIntegration] Critical error: %s", str(exc), exc_info=True)
            raise exc