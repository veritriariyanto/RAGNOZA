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
    # Filter: eksklusi pasal internal (tugas/wewenang lembaga) yang tidak
    # relevan untuk analisis kepatuhan warga sipil. Sesuaikan untuk setiap UU.
    # Catatan: Pasal 20 mengatur komposisi keanggotaan Polri, bukan sanksi disiplin.
    # Pasal 16-17 mengatur wewenang pidana Polri (penangkapan, penyitaan).
    PASAL_INTERNAL = {16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 27, 28, 29, 30}

    # Groq free tier: max 6000 TPM. Total request = system_prompt (~2500 chars)
    # + format_instructions (~4000 chars) + FAKTA (~250 chars) + KONTEKS.
    # Maka KONTEKS harus ≤ 1200 chars agar total aman.
    MAX_CONTEXT_CHARS = 1200

    # Gate kepercayaan: rerank_score (cross-encoder, sudah di-sigmoid ke 0-1 di
    # QdrantService._rerank_with_cross_encoder) tertinggi di bawah ambang ini
    # dianggap tidak cukup meyakinkan untuk dijadikan dasar generate material —
    # KECUALI hasil tersebut exact match pasal/ayat yang disebut user (exact
    # match sudah tervalidasi lewat metadata, bukan cuma similarity semantik,
    # jadi selalu dipercaya). Nilai awal 0.3 — belum dikalibrasi dengan data
    # produksi, sesuaikan berdasarkan observasi log "Confidence gate" di bawah.
    MIN_RERANK_CONFIDENCE = 0.3

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

    # ── Helper bersama: Search Qdrant + Ekstraksi & Filter Konteks ─────────
    async def _search_and_extract_context(
        self,
        knowledge_base: str,
        search_query: str,
        pasal_number,
        ayat_number,
        log_prefix: str,
    ) -> tuple[dict, list, bool, Optional[str], Optional[str]]:
        """
        Semantic search ke Qdrant (Child-Parent) lalu ekstraksi & filter konteks.

        PERBAIKAN: Gunakan pasal_number & ayat_number sebagai filter agar hasil
        search lebih relevan dengan pasal/ayat yang dimaksud user.
        PERBAIKAN KRITIS: Qdrant otomatis retry tanpa filter jika filter
        pasal/ayat menghasilkan 0 hasil → flag pasal_not_found dikembalikan.

        Return:
            (kb_results, contexts, pasal_not_found, pasal_filter, low_confidence_message)
        """
        pasal_filter = str(pasal_number) if pasal_number is not None else None
        ayat_filter = str(ayat_number) if ayat_number is not None else None
        logger.debug(
            "[%s] query=%s | pasal_filter=%s | ayat_filter=%s",
            log_prefix, search_query, pasal_filter, ayat_filter,
        )
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
                "[%s] Pasal %s tidak ditemukan di KB '%s'. "
                "Hasil bersumber dari retry tanpa filter.",
                log_prefix, pasal_filter, knowledge_base,
            )

        # Deduplikasi: hindari parent content yang sama muncul berkali-kali
        seen_parents = set()
        contexts: list = []
        context_confidences: list = []
        has_exact_match = False

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
            if child_pasal in self.PASAL_INTERNAL and not is_exact:
                logger.debug(
                    "[%s] Skip pasal internal %d (skor=%.3f)",
                    log_prefix, child_pasal, res.get("score", 0),
                )
                continue

            # Deduplikasi: skip jika parent_id sudah pernah diproses
            parent_id = res.get("child", {}).get("parent_id", "")
            if parent_id and parent_id in seen_parents:
                logger.debug(
                    "[%s] Skip duplikat parent_id=%s",
                    log_prefix, parent_id,
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
                context_confidences.append(res.get("rerank_score"))
                if is_exact:
                    has_exact_match = True
            else:
                logger.warning(
                    "[%s] Hasil Qdrant diabaikan — semua field terlalu pendek. "
                    "score=%.3f | child_content=%r | parent_content=%r",
                    log_prefix, res.get("score", 0),
                    child_content[:50], parent_content[:50],
                )

        # ── Persempit ke 1 konteks paling meyakinkan (kecuali exact match) ──
        # Tanpa exact match, `contexts` bisa berisi >1 chunk yang lolos filter
        # tapi confidence-nya jomplang jauh (mis. 1 pasal yang benar-benar
        # relevan + 1 pasal "nebeng" karena kebetulan mirip kosakata/topik).
        # Yang DIKIRIM KE LLM dipersempit ke 1 paling meyakinkan saja — supaya
        # analisis hukum tidak tercampur pasal lemah yang cuma kebetulan mirip.
        # `kb_results` (dipakai untuk source_details di response) TETAP
        # menyimpan seluruh hasil mentah yang diambil, tidak ikut dipersempit.
        if not has_exact_match and len(contexts) > 1 and any(c is not None for c in context_confidences):
            best_idx = max(
                range(len(contexts)),
                key=lambda i: context_confidences[i] if context_confidences[i] is not None else -1,
            )
            logger.info(
                "[%s] Persempit %d konteks ke 1 paling meyakinkan (confidence=%.4f) "
                "— sisanya tidak dikirim ke LLM meski tetap tercatat di source_details.",
                log_prefix, len(contexts), context_confidences[best_idx] or 0.0,
            )
            contexts = [contexts[best_idx]]
            context_confidences = [context_confidences[best_idx]]

        # ── Gate kepercayaan berbasis rerank_score ─────────────────────────
        # Konteks yang lolos filter di atas tapi skor rerank tertingginya masih
        # di bawah ambang dianggap tidak cukup meyakinkan secara topikal untuk
        # dijadikan dasar kesimpulan hukum — dikosongkan supaya jalur "tidak ada
        # context" (fallback_message) yang menangani, bukan digenerate dengan
        # percaya diri. Exact match pasal/ayat (tervalidasi via metadata, bukan
        # cuma similarity semantik) selalu bypass gate ini.
        low_confidence_message = None
        known_confidences = [c for c in context_confidences if c is not None]
        if contexts and not has_exact_match and known_confidences:
            max_confidence = max(known_confidences)
            if max_confidence < self.MIN_RERANK_CONFIDENCE:
                logger.info(
                    "[%s] Confidence gate: rerank_score tertinggi %.4f < ambang %.2f "
                    "— context dianggap tidak cukup meyakinkan, dikosongkan.",
                    log_prefix, max_confidence, self.MIN_RERANK_CONFIDENCE,
                )
                low_confidence_message = (
                    "Sistem menemukan pasal yang berpotensi terkait, namun tingkat "
                    "keyakinan (relevansi semantik) terhadap pertanyaan Anda masih "
                    "terlalu rendah untuk dijadikan dasar kesimpulan hukum yang "
                    "meyakinkan. Silakan perjelas pertanyaan Anda atau sebutkan "
                    "nomor pasal secara spesifik."
                )
                contexts = []

        return kb_results, contexts, pasal_not_found, pasal_filter, low_confidence_message

    # ── Helper bersama: Batasi Konteks per Budget Karakter + Fallback Message ──
    def _build_combined_context(
        self,
        contexts: list,
        pasal_not_found: bool,
        pasal_filter: Optional[str],
        log_prefix: str,
        low_confidence_message: Optional[str] = None,
    ) -> tuple[str, Optional[str]]:
        """
        Batasi panjang konteks per BATAS PASAL, bukan potong string mentah.
        Pasal yang tidak muat DI-SKIP UTUH (bukan dipotong setengah kalimat) —
        pasal pertama (paling relevan, karena `contexts` sudah terurut sesuai
        skor) selalu disertakan penuh meski sendirian sudah melebihi budget.

        Return:
            (combined_context, fallback_message)
        """
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

        budget = self.MAX_CONTEXT_CHARS - len(catatan_prefix)
        selected_contexts: list = []
        used_chars = 0
        for ctx in contexts:
            added_len = len(ctx) + (2 if selected_contexts else 0)  # pemisah "\n\n"
            if selected_contexts and used_chars + added_len > budget:
                logger.warning(
                    "[%s] %d dari %d pasal di-skip (utuh, bukan dipotong) "
                    "karena melebihi budget konteks (%d chars).",
                    log_prefix, len(contexts) - len(selected_contexts),
                    len(contexts), self.MAX_CONTEXT_CHARS,
                )
                break
            selected_contexts.append(ctx)
            used_chars += added_len

        combined_context = catatan_prefix + "\n\n".join(selected_contexts)

        logger.info(
            "[%s] Context terkumpul: %d/%d chunk, total %d chars",
            log_prefix, len(selected_contexts), len(contexts), len(combined_context),
        )

        fallback_message = None
        if not contexts:
            # Bedakan pesan fallback berdasarkan apakah gagal karena gate
            # kepercayaan, pasal disebut tapi tidak ketemu, atau benar-benar
            # tidak ada konteks sama sekali
            if low_confidence_message:
                fallback_message = low_confidence_message
            elif pasal_not_found:
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

        return combined_context, fallback_message

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

            # ── Tahap 3-4: Semantic Search + Ekstraksi & Filter Konteks ───────
            kb_results, contexts, pasal_not_found, pasal_filter, low_confidence_message = await self._search_and_extract_context(
                knowledge_base=knowledge_base,
                search_query=search_query,
                pasal_number=pasal_number,
                ayat_number=ayat_number,
                log_prefix="RAGIntegration",
            )

            combined_context, fallback_message = self._build_combined_context(
                contexts=contexts,
                pasal_not_found=pasal_not_found,
                pasal_filter=pasal_filter,
                log_prefix="RAGIntegration",
                low_confidence_message=low_confidence_message,
            )

            # ── Tahap 5: Generate Material ────────────────────────────────────
            final_material = None
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

            # ── Tahap 2-3: Semantic Search + Ekstraksi & Filter Konteks ───────
            kb_results, contexts, pasal_not_found, pasal_filter, low_confidence_message = await self._search_and_extract_context(
                knowledge_base=knowledge_base,
                search_query=search_query,
                pasal_number=pasal_number,
                ayat_number=ayat_number,
                log_prefix="TextPipeline",
            )

            combined_context, fallback_message = self._build_combined_context(
                contexts=contexts,
                pasal_not_found=pasal_not_found,
                pasal_filter=pasal_filter,
                log_prefix="TextPipeline",
                low_confidence_message=low_confidence_message,
            )

            # ── Tahap 4: Generate Material ────────────────────────────────────
            final_material = None
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
