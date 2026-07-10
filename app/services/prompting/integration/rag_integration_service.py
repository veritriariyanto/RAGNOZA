#app/services/prompting/integration/rag_integration_service.py

import logging
from typing import Optional

from fastapi import BackgroundTasks

from app.services.prompting.audio.stt_service import STTService
from app.services.prompting.prompt.repair_text import TextRefinerService
from app.services.knowlagebase.qdrant_service import QdrantService
from app.services.prompting.prompt.generate_content_service import (
    MaterialGeneratorService,
    SYSTEM_ERROR_FALLBACK_MESSAGE,   # ← tambahan
)
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
            # PERBAIKAN: Gunakan pasal_number & ayat_number sebagai filter agar
            # hasil search lebih relevan dengan pasal/ayat yang dimaksud user.
            # PERBAIKAN KRITIS: Qdrant otomatis retry tanpa filter jika filter
            # pasal/ayat menghasilkan 0 hasil → flag pasal_not_found dikembalikan.
            pasal_filter = str(pasal_number) if pasal_number is not None else None
            ayat_filter = str(ayat_number) if ayat_number is not None else None
            print(f"Nilai query: {search_query} | pasal_filter: {pasal_filter} | ayat_filter: {ayat_filter}")
            kb_results = await self.vector_service.search_knowledgebase(
                base_name=knowledge_base,
                query=search_query,
                pasal_type=pasal_filter,
                ayat_type=ayat_filter,
                limit=2,  # PERBAIKAN: turunkan dari 3 ke 2 agar token tidak overflow
            )

            # ── Cek apakah pasal yang disebut user tidak ditemukan di KB ──
            pasal_not_found = kb_results.get("pasal_not_found", False)
            if pasal_not_found:
                logger.info(
                    "[RAGIntegration] Pasal %s tidak ditemukan di KB '%s'. "
                    "Hasil bersumber dari retry tanpa filter.",
                    pasal_filter, knowledge_base,
                )

            # ── DEBUG SEMENTARA: lihat struktur penuh result pertama ──
            if kb_results.get("results"):
                first = kb_results["results"][0]
                logger.debug("[RAGIntegration] Qdrant sample child keys: %s", list(
                    first.get("child", {}).keys()))
                logger.debug("[RAGIntegration] Qdrant sample parent keys: %s", list(
                    first.get("parent", {}).keys()))

            # ── Tahap 4: Ekstraksi & Filter Konteks ──────────────────────────────
            # Deduplikasi: hindari parent content yang sama muncul berkali-kali
            seen_parents = set()
            contexts = []
            
            # Filter: eksklusi pasal internal (tugas/wewenang lembaga) yang tidak
            # relevan untuk analisis kepatuhan warga sipil. Sesuaikan untuk setiap UU.
            PASAL_INTERNAL = {16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 27, 28, 29, 30}
            # Catatan: Pasal 20 mengatur komposisi keanggotaan Polri, bukan sanksi disiplin.
            # Pasal 16-17 mengatur wewenang pidana Polri (penangkapan, penyitaan).

            for res in kb_results.get("results", []):
                # Cek apakah hasil ini exact match dengan pasal user
                is_exact = res.get("is_exact_pasal_match", False) or \
                           res.get("is_exact_ayat_match", False)
                
                # Ambil nomor pasal — fallback ke pasal_rujukan (chunk Penjelasan)
                # lalu ke parent jika child tidak punya metadata pasal sama sekali
                child_pasal = res.get("child", {}).get("pasal")
                if child_pasal is None:
                    child_pasal = res.get("child", {}).get("pasal_rujukan")
                if child_pasal is None:
                    child_pasal = res.get("parent", {}).get("pasal")
                if child_pasal is None:
                    child_pasal = res.get("parent", {}).get("pasal_rujukan")
                
                # Skip pasal internal (kecuali itu exact match dengan yang disebut user)
                if child_pasal in PASAL_INTERNAL and not is_exact:
                    logger.debug(
                        "[RAGIntegration] Skip pasal internal %d (skor=%.3f)",
                        child_pasal, res.get("score", 0),
                    )
                    continue

                # Deduplikasi: skip jika parent_id sudah pernah diproses
                parent_id = res.get("child", {}).get("parent_id", "")
                if parent_id and parent_id in seen_parents:
                    logger.debug(
                        "[RAGIntegration] Skip duplikat parent_id=%s",
                        parent_id,
                    )
                    continue
                if parent_id:
                    seen_parents.add(parent_id)

                # Prioritas pengambilan konten — dari yang paling lengkap
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
                        "[RAGIntegration] Hasil Qdrant diabaikan — semua field terlalu pendek. "
                        "score=%.3f | child_content=%r | parent_content=%r",
                        res.get("score", 0),
                        child_content[:50],
                        parent_content[:50],
                    )

            # ── Batasi panjang konteks per BATAS PASAL, bukan potong string mentah ──
            # Groq free tier: max 6000 TPM. Total request = system_prompt (~2500 chars)
            # + format_instructions (~4000 chars) + FAKTA (~250 chars) + KONTEKS.
            # Maka KONTEKS harus ≤ 1200 chars agar total aman. Pasal yang tidak muat
            # DI-SKIP UTUH (bukan dipotong setengah kalimat) — pasal pertama (paling
            # relevan, karena `contexts` sudah terurut sesuai skor) selalu disertakan
            # penuh meski sendirian sudah melebihi budget.
            MAX_CONTEXT_CHARS = 1200

            catatan_prefix = ""
            if pasal_not_found and contexts:
                catatan_prefix = (
                    f"CATATAN SISTEM: Nomor pasal yang disebutkan pengguna "
                    f"(Pasal {pasal_filter}) TIDAK DITEMUKAN di knowledge base. "
                    f"Konteks hukum berikut bersumber dari pasal-pasal LAIN yang "
                    f"relevan dengan topik query.\n"
                    f"IMBAUAN: Jangan simpulkan tindakan pengguna sebagai "
                    f"'Patuh'/'aman' semata karena pasal yang disebutkan tidak ada. "
                    f"NAMUN DEMIKIAN, 'tetap evaluasi tindakan' BUKAN berarti "
                    f"memaksakan korelasi ke pasal yang TIDAK RELEVAN secara "
                    f"substansi. Pasal internal (mengatur tugas/wewenang lembaga) "
                    f"tidak boleh dijadikan dasar kesimpulan pelanggaran warga "
                    f"sipil. Jika tidak ada pasal yang tepat, akui keterbatasan "
                    f"konteks secara jujur.\n\n"
                )

            budget = MAX_CONTEXT_CHARS - len(catatan_prefix)
            selected_contexts: list = []
            used_chars = 0
            for ctx in contexts:
                added_len = len(ctx) + (2 if selected_contexts else 0)  # pemisah "\n\n"
                if selected_contexts and used_chars + added_len > budget:
                    logger.warning(
                        "[RAGIntegration] %d dari %d pasal di-skip (utuh, bukan dipotong) "
                        "karena melebihi budget konteks (%d chars).",
                        len(contexts) - len(selected_contexts), len(contexts), MAX_CONTEXT_CHARS,
                    )
                    break
                selected_contexts.append(ctx)
                used_chars += added_len

            combined_context = catatan_prefix + "\n\n".join(selected_contexts)

            logger.info(
                "[RAGIntegration] Context terkumpul: %d/%d chunk, total %d chars",
                len(selected_contexts), len(contexts), len(combined_context)
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

            else:
                # Bedakan pesan fallback berdasarkan apakah pasal disebut tapi error,
                # atau benar-benar tidak ada konteks sama sekali
                if pasal_not_found:
                    fallback_message = (
                        "Pasal yang Anda sebutkan tidak ditemukan di Knowledge Base, "
                        "dan tidak ada pasal lain yang cukup relevan dengan topik "
                        "pertanyaan. Silakan tambahkan dokumen hukum yang memuat pasal "
                        "tersebut, atau perluas cakupan knowledge base."
                    )
                else:
                    fallback_message = (
                        "Tidak ada konteks hukum yang cukup relevan ditemukan di "
                        "Knowledge Base untuk pertanyaan Anda. Coba tambahkan detail "
                        "lebih spesifik atau gunakan knowledge base yang berbeda."
                    )

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

            # FIX (arsitektur baru): evaluasi RAGAS sekarang DITUNGGU (synchronous),
            # bukan lagi background task. Alasan: user ingin generate + evaluasi
            # selesai SEBELUM redirect ke halaman hasil, bukan redirect duluan lalu
            # skor evaluasi menyusul belakangan.
            # KONSEKUENSI: response ke user akan tertunda hingga evaluasi selesai
            # (bisa 1-3 menit tergantung antrian rate-limit Groq/TPM).
            ragas_result = None
            if auto_evaluate and combined_context and final_material:
                ragas_result = await trigger_auto_evaluation(
                    question=search_query,
                    context=combined_context,
                    material=final_material,
                    ground_truth=None,
                    source_label="rag_pipeline",
                    history_id=history_id,
                    context_chunks=contexts,
                )

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
                fallback_message=fallback_message,
                ragas_status=ragas_result.get("status") if ragas_result else None,
                ragas_metrics=ragas_result.get("metrics") if ragas_result else None,
                ragas_error=ragas_result.get("error") if ragas_result else None,
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
        ground_truth: Optional[str] = None,   # ← baru, default None
        is_dataset_eval: bool = False,   # ← tambahan baru
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
            # PERBAIKAN: Gunakan pasal_number & ayat_number sebagai filter agar
            # hasil search lebih relevan dengan pasal/ayat yang dimaksud user.
            # PERBAIKAN KRITIS: Qdrant otomatis retry tanpa filter jika filter
            # pasal/ayat menghasilkan 0 hasil → flag pasal_not_found dikembalikan.
            pasal_filter = str(pasal_number) if pasal_number is not None else None
            ayat_filter = str(ayat_number) if ayat_number is not None else None
            print(f"Nilai query: {search_query} | pasal_filter: {pasal_filter} | ayat_filter: {ayat_filter}")
            kb_results = await self.vector_service.search_knowledgebase(
                base_name=knowledge_base,
                query=search_query,
                pasal_type=pasal_filter,
                ayat_type=ayat_filter,
                limit=2,  # PERBAIKAN: turunkan dari 3 ke 2 agar token tidak overflow
            )

            # ── Cek apakah pasal yang disebut user tidak ditemukan di KB ──
            pasal_not_found = kb_results.get("pasal_not_found", False)
            if pasal_not_found:
                logger.info(
                    "[TextPipeline] Pasal %s tidak ditemukan di KB '%s'. "
                    "Hasil bersumber dari retry tanpa filter.",
                    pasal_filter, knowledge_base,
                )

            # ── Tahap 3: Ekstraksi & Filter Konteks ────────────────────────────
            seen_parents = set()
            contexts = []
            
            # Filter: eksklusi pasal internal (sama seperti di audio pipeline)
            PASAL_INTERNAL = {16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 27, 28, 29, 30}
            # Catatan: Pasal 20 mengatur komposisi keanggotaan Polri, bukan sanksi disiplin.
            # Pasal 16-17 mengatur wewenang pidana Polri (penangkapan, penyitaan).

            for res in kb_results.get("results", []):
                # Cek apakah hasil ini exact match dengan pasal user
                is_exact = res.get("is_exact_pasal_match", False) or \
                           res.get("is_exact_ayat_match", False)
                
                # Ambil nomor pasal — fallback ke pasal_rujukan (chunk Penjelasan)
                # lalu ke parent jika child tidak punya metadata pasal sama sekali
                child_pasal = res.get("child", {}).get("pasal")
                if child_pasal is None:
                    child_pasal = res.get("child", {}).get("pasal_rujukan")
                if child_pasal is None:
                    child_pasal = res.get("parent", {}).get("pasal")
                if child_pasal is None:
                    child_pasal = res.get("parent", {}).get("pasal_rujukan")
                
                # Skip pasal internal (kecuali exact match)
                if child_pasal in PASAL_INTERNAL and not is_exact:
                    logger.debug(
                        "[TextPipeline] Skip pasal internal %d (skor=%.3f)",
                        child_pasal, res.get("score", 0),
                    )
                    continue

                # Deduplikasi parent_id
                parent_id = res.get("child", {}).get("parent_id", "")
                if parent_id and parent_id in seen_parents:
                    logger.debug(
                        "[TextPipeline] Skip duplikat parent_id=%s",
                        parent_id,
                    )
                    continue
                if parent_id:
                    seen_parents.add(parent_id)

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

            # ── Batasi panjang konteks per BATAS PASAL, bukan potong string mentah ──
            # Pasal yang tidak muat DI-SKIP UTUH (bukan dipotong setengah kalimat) —
            # pasal pertama (paling relevan) selalu disertakan penuh meski sendirian
            # sudah melebihi budget.
            MAX_CONTEXT_CHARS = 1200

            catatan_prefix = ""
            if pasal_not_found and contexts:
                catatan_prefix = (
                    f"CATATAN SISTEM: Nomor pasal yang disebutkan pengguna "
                    f"(Pasal {pasal_filter}) TIDAK DITEMUKAN di knowledge base. "
                    f"Konteks hukum berikut bersumber dari pasal-pasal LAIN yang "
                    f"relevan dengan topik query.\n"
                    f"IMBAUAN: Jangan simpulkan tindakan pengguna sebagai "
                    f"'Patuh'/'aman' semata karena pasal yang disebutkan tidak ada. "
                    f"NAMUN DEMIKIAN, 'tetap evaluasi tindakan' BUKAN berarti "
                    f"memaksakan korelasi ke pasal yang TIDAK RELEVAN secara "
                    f"substansi. Pasal internal (mengatur tugas/wewenang lembaga) "
                    f"tidak boleh dijadikan dasar kesimpulan pelanggaran warga "
                    f"sipil. Jika tidak ada pasal yang tepat, akui keterbatasan "
                    f"konteks secara jujur.\n\n"
                )

            budget = MAX_CONTEXT_CHARS - len(catatan_prefix)
            selected_contexts: list = []
            used_chars = 0
            for ctx in contexts:
                added_len = len(ctx) + (2 if selected_contexts else 0)  # pemisah "\n\n"
                if selected_contexts and used_chars + added_len > budget:
                    logger.warning(
                        "[TextPipeline] %d dari %d pasal di-skip (utuh, bukan dipotong) "
                        "karena melebihi budget konteks (%d chars).",
                        len(contexts) - len(selected_contexts), len(contexts), MAX_CONTEXT_CHARS,
                    )
                    break
                selected_contexts.append(ctx)
                used_chars += added_len

            combined_context = catatan_prefix + "\n\n".join(selected_contexts)

            logger.info(
                "[TextPipeline] Context terkumpul: %d/%d chunk, total %d chars",
                len(selected_contexts), len(contexts), len(combined_context)
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

            else:
                # Bedakan pesan fallback berdasarkan apakah pasal disebut tapi error,
                # atau benar-benar tidak ada konteks sama sekali
                if pasal_not_found:
                    fallback_message = (
                        "Pasal yang Anda sebutkan tidak ditemukan di Knowledge Base, "
                        "dan tidak ada pasal lain yang cukup relevan dengan topik "
                        "pertanyaan. Silakan tambahkan dokumen hukum yang memuat pasal "
                        "tersebut, atau perluas cakupan knowledge base."
                    )
                else:
                    fallback_message = (
                        "Tidak ada konteks hukum yang cukup relevan ditemukan di "
                        "Knowledge Base untuk pertanyaan Anda. Coba tambahkan detail "
                        "lebih spesifik atau gunakan knowledge base yang berbeda."
                    )

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

            # ── Tahap 6 (DIPINDAH KE SINI — FIX BUG KRITIS): Evaluasi RAGAS 
            ragas_result = None

            # FIX (dataset_eval_live cemar fallback): saat is_dataset_eval=True,
            # generate_legal_material bisa gagal total (semua attempt LLM gagal)
            # dan mengembalikan MaterialResponse fallback berisi
            # SYSTEM_ERROR_FALLBACK_MESSAGE di ringkasan[0].poin. Tanpa guard ini,
            # trigger_auto_evaluation tetap terpanggil untuk source_label
            # "dataset_eval_live" SEBELUM dataset_runner_service.py sempat
            # mendeteksi & skip item ini — mencemari agregat skor dataset eval
            # dengan skor atas teks error, bukan jawaban hukum riil.
            # Scope sengaja dibatasi ke is_dataset_eval=True saja agar jalur
            # produksi (text_pipeline/rag_pipeline) tidak berubah perilakunya.
            is_system_error_result = bool(
                is_dataset_eval
                and final_material
                and final_material.ringkasan
                and final_material.ringkasan[0].poin == SYSTEM_ERROR_FALLBACK_MESSAGE
            )

            if auto_evaluate and combined_context and final_material and not is_system_error_result:
                ragas_result = await trigger_auto_evaluation(
                    question=search_query,
                    context=combined_context,
                    material=final_material,
                    ground_truth=ground_truth,     # ← diubah dari None hardcoded menjadi parameter
                    source_label="dataset_eval_live" if is_dataset_eval else "text_pipeline",                    
                    history_id=history_id,
                    context_chunks=contexts,
                )
            elif is_system_error_result:
                logger.warning(
                    "[TextPipeline] SYSTEM_ERROR terdeteksi pada is_dataset_eval=True — "
                    "trigger_auto_evaluation (dataset_eval_live) dilewati agar tidak "
                    "mencemari skor RAGAS."
                )

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
                fallback_message=fallback_message,
                ragas_status=ragas_result.get("status") if ragas_result else None,
                ragas_metrics=ragas_result.get("metrics") if ragas_result else None,
                ragas_error=ragas_result.get("error") if ragas_result else None,
            )

        except Exception as exc:
            logger.error("[TextPipeline] Critical error: %s",
                         str(exc), exc_info=True)
            raise exc
