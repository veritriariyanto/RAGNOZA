# app/services/history/rag_history_service.py

# ⚠️ DEPRECATED — TIDAK DIPAKAI JALUR MANAPUN YANG AKTIF (per audit Fase 0 RAGAS, Juli 2026).
# Jalur history yang aktif sekarang: SessionService (app/services/history/session_service.py)
# yang menulis ke model RAGProcess, bukan LegalMaterialHistory di sini.
# Kandidat untuk dihapus penuh (bersama app/database/migration/history.py) setelah
# dikonfirmasi tidak ada dependency tersembunyi (test suite, script manual, dsb).

import logging
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi.encoders import jsonable_encoder

# 1. Sesuaikan import model dengan hasil migrasi terbarumu
from app.database.migration.history import LegalMaterialHistory

logger = logging.getLogger(__name__)

class RAGHistoryService:
    @staticmethod
    def save_history(
        db: Session,
        knowledge_base: str,
        provider: str,
        raw_transcribe: str,
        repaired_text: str,
        search_query: str,
        retrieved_context: str,
        final_material,
        fallback_message: str | None = None,
    ):
        try:
            # 2. Bikin default title agar bisa kamu edit sewaktu-waktu lewat Python
            waktu_sekarang = datetime.now().strftime("%Y-%m-%d %H:%M")
            default_title = f"Analisis {knowledge_base.replace('_', ' ').title()} - {waktu_sekarang}"

            # 3. Konversi Pydantic object ke Python Dict murni (Tanpa json.dumps!)
            # Menggunakan jsonable_encoder dari FastAPI agar tipe data aneh otomatis aman jadi dict
            clean_material = jsonable_encoder(final_material) if final_material else None

            # 4. Satukan parameter pencarian RAG ke dalam satu struktur metadata JSONB
            rag_meta = {
                "query_used": search_query,
                "has_context": bool(retrieved_context),
                "retrieved_context_preview": retrieved_context[:500] if retrieved_context else None
            }

            # 5. Petakan ke model database baru
            history = LegalMaterialHistory(
                title=default_title,
                status="success" if final_material else "failed",
                provider=provider,
                knowledge_base=knowledge_base,
                transcription_raw=raw_transcribe,
                transcription_repaired=repaired_text,
                rag_metadata=rag_meta,
                generated_material=clean_material,
                # Catatan: compliance_score & decision_status otomatis ikut tersimpan 
                # di dalam payload JSONB `generated_material.risk_review` bawaan LLM Anda.
                evaluation={
                    "status": "running_in_background" if final_material else "failed",
                    "note": fallback_message if fallback_message else "Evaluasi RAGAS berjalan otomatis di background."
                }
            )

            db.add(history)
            db.commit()
            db.refresh(history)

            logger.info(f"[HistoryDB] Berhasil menyimpan riwayat baru dengan ID: {history.id}")
            return history

        except Exception as e:
            db.rollback()
            logger.error(f"[HistoryDB] Gagal menyimpan history: {str(e)}", exc_info=True)
            return None