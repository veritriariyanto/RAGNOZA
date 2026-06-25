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
from app.services.knowlagebase.qdrant_service import QdrantService
from app.services.prompting.prompt.generate_content_service import MaterialGeneratorService
from app.schemas.prompting.generate_content import MaterialRequest
from app.schemas.prompting.integration import RAGIntegrationResponse

from sqlalchemy.orm import Session
from app.services.evaluation.formatter import material_to_text
from app.services.history.session_service import SessionService              # ← fix import
from app.services.evaluation.evaluation_hook import trigger_auto_evaluation

logger = logging.getLogger(__name__)


class RAGIntegrationService:
    def __init__(
        self,
        stt_service: STTService,
        text_service: TextRefinerService,
        vector_service: QdrantService,
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
        auto_evaluate: bool = True,
        session_id: int | None = None,
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
            pasal_number = refinement.get("pasal_number")
            ayat_number = refinement.get("ayat_number")

            # ── Tahap 3: Semantic Search ke Qdrant (Child-Parent) ─────────────
            # PERBAIKAN: Gunakan pasal_number sebagai filter agar hasil search
            # lebih relevan dengan pasal yang dimaksud user.
            pasal_filter = str(pasal_number) if pasal_number is not None else None
            kb_results = await self.vector_service.search_knowledgebase(
                base_name=knowledge_base,
                query=search_query,
                pasal_type=pasal_filter,
                limit=3,
            )

            # ── DEBUG SEMENTARA: lihat struktur penuh result pertama ──
            if kb_results.get("results"):
                first = kb_results["results"][0]
                logger.debug("[RAGIntegration] Qdrant sample child keys: %s", list(
                    first.get("child", {}).keys()))
                logger.debug("[RAGIntegration] Qdrant sample parent keys: %s", list(
                    first.get("parent", {}).keys()))

            # ── Tahap 4: Ekstraksi Konteks ─────────────────────────────────────────
            contexts = []
            for res in kb_results.get("results", []):
                # Prioritas pengambilan konten — dari yang paling lengkap
                # 1. parent.content (full pasal/section)
                # 2. child.content (chunk dengan prefix lengkap)
                # 3. child.raw_text (teks mentah tanpa prefix)

                content = None

                parent_content = res.get("parent", {}).get("content", "")
                child_content = res.get("child", {}).get("content", "")
                child_raw = res.get("child", {}).get("raw_text", "")

                if parent_content and len(parent_content.strip()) > 30:
                    content = parent_content.strip()
                elif child_content and len(child_content.strip()) > 30:
                    content = child_content.strip()
                elif child_raw and len(child_raw.strip()) > 30:
                    content = child_raw.strip()

                if content:
                    contexts.append(content)
                else:
                    # Log supaya kita tahu data mana yang kosong
                    logger.warning(
                        "[RAGIntegration] Hasil Qdrant diabaikan — semua field terlalu pendek. "
                        "score=%.3f | child_content=%r | parent_content=%r",
                        res.get("score", 0),
                        child_content[:50],
                        parent_content[:50],
                    )

            combined_context = "\n\n".join(contexts)

            logger.info(
                "[RAGIntegration] Context terkumpul: %d chunk, total %d chars",
                len(contexts), len(combined_context)
            )

            # Debug sementara
            print(f"[SERVICE DEBUG] contexts count: {len(contexts)}")
            print(
                f"[SERVICE DEBUG] combined_context length: {len(combined_context)}")
            print(f"[SERVICE DEBUG] sample: {combined_context[:200]}")

            # ── Tahap 5: Generate Material ────────────────────────────────────
            final_material = None
            fallback_message = None
            history_id = None
            rag_session_id = session_id

            if contexts:
                material_payload = MaterialRequest(
                    context_text=(
                        f"KONTEKS HUKUM:\n{combined_context}"
                        f"\n\nFAKTA/TRANSKRIPSI:\n{repaired_text}"
                    ),
                    user_scenario=repaired_text,
                    raw_transcribe=raw_transcribe,
                )
                final_material = await self.material_service.generate_legal_material(
                    material_payload
                )

                # ── Tahap 7: Jalankan Evaluasi di Background Task ──────────────
                if auto_evaluate and background_tasks and combined_context and final_material:
                    background_tasks.add_task(
                        trigger_auto_evaluation,
                        question=search_query,
                        context=combined_context,
                        material=final_material,
                        ground_truth=None,
                        source_label="rag_pipeline",
                        history_id=history_id
                    )
            else:
                fallback_message = "Tidak ada konteks hukum yang cukup relevan ditemukan di Knowledge Base."

            # ── Tahap 6: Simpan History (SELALU dijalankan, baik ada context maupun tidak) ──
            session_title = (
                repaired_text[:80]
                if repaired_text
                else raw_transcribe[:80]
                if raw_transcribe
                else "Session Tanpa Judul"
            )
            saved_history = SessionService.save_history(
                db=self.db,
                session_id=rag_session_id,
                session_title=session_title,
                knowledge_base=knowledge_base,
                provider=provider,
                raw_transcribe=raw_transcribe,
                repaired_text=repaired_text,
                search_query=search_query,
                retrieved_context=combined_context,
                final_material=final_material,
            )
            history_id = saved_history.id if saved_history else None
            rag_session_id = saved_history.session_id if saved_history else rag_session_id


           # ── Tahap 8: Return Response Ter validasi ─────────────────────────
            return RAGIntegrationResponse(
                raw_transcribe=raw_transcribe,
                final_repaired_text=repaired_text,
                # 💡 TAMBAHKAN INI: Memenuhi kewajiban schema Pydantic
                user_scenario=repaired_text,
                search_query_used=search_query,
                has_context=bool(contexts),
                retrieved_context=combined_context,
                source_details=kb_results.get("results", []),
                history_id=history_id,
                session_id=rag_session_id,
                final_material=final_material,
                fallback_message=fallback_message
            )

        except Exception as exc:
            logger.error("[RAGIntegration] Critical error: %s",
                         str(exc), exc_info=True)
            raise exc

    async def process_text_to_material(
        self,
        raw_text: str,
        knowledge_base: str = "uud_1945",
        style: str = "formal",
        background_tasks: Optional[BackgroundTasks] = None,
        auto_evaluate: bool = True,
        session_id: int | None = None,
    ) -> RAGIntegrationResponse:
        """
        Pipeline dari teks (tanpa STT): Repair → Search → Generate Material → Save → Eval

        Digunakan ketika user sudah punya hasil transkripsi dan ingin menjalankan
        pipeline RAG dari teks tersebut (setelah review/edit manual).

        Args:
            raw_text          : Teks transkripsi yang sudah ada
            knowledge_base    : Nama collection Qdrant yang dipakai
            style             : Gaya penulisan material
            background_tasks  : FastAPI BackgroundTasks untuk eval RAGAS
            auto_evaluate     : Apakah jalankan evaluasi RAGAS di background
            session_id        : ID sesi RAG yang sudah ada

        Returns:
            RAGIntegrationResponse — hasil pipeline RAG lengkap
        """
        try:
            # ── Tahap 1: Repair Text & Generate Search Query ──────────────────
            refinement = await self.text_service.repair_legal_text(raw_text)
            repaired_text = refinement["repaired_text"]
            search_query = refinement["search_query"]
            pasal_number = refinement.get("pasal_number")
            ayat_number = refinement.get("ayat_number")

            # ── Tahap 2: Semantic Search ke Qdrant (Child-Parent) ─────────────
            # PERBAIKAN: Gunakan pasal_number sebagai filter agar hasil search
            # lebih relevan dengan pasal yang dimaksud user.
            pasal_filter = str(pasal_number) if pasal_number is not None else None
            kb_results = await self.vector_service.search_knowledgebase(
                base_name=knowledge_base,
                query=search_query,
                pasal_type=pasal_filter,
                limit=3,
            )

            # ── Tahap 3: Ekstraksi Konteks ────────────────────────────────────
            contexts = []
            for res in kb_results.get("results", []):
                content = None
                parent_content = res.get("parent", {}).get("content", "")
                child_content = res.get("child", {}).get("content", "")
                child_raw = res.get("child", {}).get("raw_text", "")

                if parent_content and len(parent_content.strip()) > 30:
                    content = parent_content.strip()
                elif child_content and len(child_content.strip()) > 30:
                    content = child_content.strip()
                elif child_raw and len(child_raw.strip()) > 30:
                    content = child_raw.strip()

                if content:
                    contexts.append(content)
                else:
                    logger.warning(
                        "[TextPipeline] Hasil Qdrant diabaikan — semua field terlalu pendek. "
                        "score=%.3f | child_content=%r | parent_content=%r",
                        res.get("score", 0),
                        child_content[:50],
                        parent_content[:50],
                    )

            combined_context = "\n\n".join(contexts)

            logger.info(
                "[TextPipeline] Context terkumpul: %d chunk, total %d chars",
                len(contexts), len(combined_context)
            )

            # ── Tahap 4: Generate Material ────────────────────────────────────
            final_material = None
            fallback_message = None
            history_id = None
            rag_session_id = session_id

            if contexts:
                material_payload = MaterialRequest(
                    context_text=(
                        f"KONTEKS HUKUM:\n{combined_context}"
                        f"\n\nFAKTA/TRANSKRIPSI:\n{repaired_text}"
                    ),
                    user_scenario=repaired_text,
                    raw_transcribe=raw_text,
                )
                final_material = await self.material_service.generate_legal_material(
                    material_payload
                )

                # ── Tahap 6: Evaluasi RAGAS di Background ─────────────────────
                if auto_evaluate and background_tasks and combined_context and final_material:
                    background_tasks.add_task(
                        trigger_auto_evaluation,
                        question=search_query,
                        context=combined_context,
                        material=final_material,
                        ground_truth=None,
                        source_label="text_pipeline",
                        history_id=history_id
                    )
            else:
                fallback_message = "Tidak ada konteks hukum yang cukup relevan ditemukan di Knowledge Base."

            # ── Tahap 5: Simpan History (SELALU dijalankan, baik ada context maupun tidak) ──
            session_title = repaired_text[:80] if repaired_text else "Session Tanpa Judul"
            saved_history = SessionService.save_history(
                db=self.db,
                session_id=rag_session_id,
                session_title=session_title,
                knowledge_base=knowledge_base,
                provider="text_input",
                raw_transcribe=raw_text,
                repaired_text=repaired_text,
                search_query=search_query,
                retrieved_context=combined_context,
                final_material=final_material,
            )
            history_id = saved_history.id if saved_history else None
            rag_session_id = saved_history.session_id if saved_history else rag_session_id

            # ── Return Response ────────────────────────────────────────────────

            return RAGIntegrationResponse(
                raw_transcribe=raw_text,
                final_repaired_text=repaired_text,
                user_scenario=repaired_text,
                search_query_used=search_query,
                has_context=bool(contexts),
                retrieved_context=combined_context,
                source_details=kb_results.get("results", []),
                history_id=history_id,
                session_id=rag_session_id,
                final_material=final_material,
                fallback_message=fallback_message
            )

        except Exception as exc:
            logger.error("[TextPipeline] Critical error: %s",
                         str(exc), exc_info=True)
            raise exc
