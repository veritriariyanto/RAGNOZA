#app/services/history/session_service.py

import json 
import logging

from sqlalchemy.orm import Session

from app.database.models.rag_process import RAGProcess
from app.database.models.rag_session import RAGSession

logger = logging.getLogger(__name__)

class SessionService:

    @staticmethod
    def _get_or_create_session(
            db: Session,
            session_id: int | None,
            session_title: str | None,
            knowledge_base: str,
            provider: str,
        ) -> RAGSession | None:
            """
            FUNGSI INTERNAL (Helper): Mencari sesi percakapan yang sudah ada berdasarkan ID,
            atau otomatis membuat baris sesi (RAGSession) baru jika belum terdaftar.
            """
            if session_id is not None:
                existing_session = db.query(RAGSession).filter(RAGSession.id == session_id).first()
                if existing_session:
                    return existing_session

            session = RAGSession(
                session_title=session_title,
                knowledge_base=knowledge_base,
                provider=provider,
            )
            db.add(session)
            db.flush()
            return session    

    @staticmethod
    def save_history(
            db: Session,
            session_title: str | None,
            knowledge_base: str,
            provider: str,
            raw_transcribe: str,
            repaired_text: str,
            search_query: str,
            retrieved_context: str,
            final_material,
            session_id: int | None = None,
        ) -> RAGProcess | None:
            """
            Menyimpan rekaman penuh alur RAG Pipeline (Mulai dari teks suara hingga materi hukum final).
            Menghubungkan tabel RAGProcess dengan tabel induk RAGSession.
            """
            try:
                session = SessionService._get_or_create_session(
                    db=db,
                    session_id=session_id,
                    session_title=session_title,
                    knowledge_base=knowledge_base,  
                    provider=provider,
                )

                if session is None:
                    raise RuntimeError("Gagal membuat atau memuat rag_session")

                process = RAGProcess(
                    session_id=session.id,
                    title=session_title,
                    raw_transcribe=raw_transcribe,
                    repaired_text=repaired_text,
                    search_query=search_query,
                    retrieved_context=retrieved_context,
                    generated_material=(
                        json.dumps(final_material.model_dump(), ensure_ascii=False)
                        if final_material else None
                    ),
                    compliance_score=(
                        final_material.compliance_score if final_material else None
                    ),
                    decision_status=(
                        final_material.decision_status if final_material else None
                    ),
                )

                db.add(process)
                db.commit()
                db.refresh(process)

                logger.info(
                    "[RAGHistory] Tersimpan — session_id=%d | process_id=%d | kb=%s | score=%s | status=%s",
                    session.id,
                    process.id,
                    knowledge_base,
                    process.compliance_score,
                    process.decision_status,
                )
                return process

            except Exception as exc:
                db.rollback()
                logger.error("[RAGHistory] Gagal simpan: %s", exc, exc_info=True)
                return None
        

    @staticmethod
    def update_title(
        db: Session,
        history_id: int,
        session_title: str,
    ) -> bool:
        """
        Mengubah judul satu item riwayat (RAGProcess) berdasarkan history_id.
        Digunakan saat user mengganti judul chat di panel UI sidebar Streamlit.

        PERBAIKAN: sebelumnya judul disimpan di RAGSession.session_title —
        karena satu session bisa punya banyak RAGProcess (generate berulang
        dalam sesi browser yang sama, lihat rag_session_id di
        streamlit_app/utils/session.py), mengedit judul satu item di sidebar
        ikut mengubah SEMUA item lain yang berbagi session_id yang sama.
        Judul sekarang disimpan per-RAGProcess supaya tiap item independen.
        """
        try:
            process = (
                db.query(RAGProcess)
                .filter(RAGProcess.id == history_id)
                .first()
            )

            if not process:
                logger.warning(
                    "[RAGHistory] update_title: process_id=%d tidak ditemukan",
                    history_id
                )
                return False

            process.title = session_title.strip()

            db.commit()

            logger.info(
                "[RAGHistory] Title updated — process_id=%d | title=%s",
                process.id,
                session_title,
            )

            return True

        except Exception as exc:
            db.rollback()
            logger.error(
                "[RAGHistory] Gagal update title: %s",
                exc,
                exc_info=True
            )
            return False