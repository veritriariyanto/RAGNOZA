#app/services/evaluation/evaluation_db_service.py

import logging

logger = logging.getLogger(__name__)

def update_ragas_in_db(history_id: int, result: dict) -> None:
    """
    Menyimpan atau memperbarui skor metrik hasil RAGAS ke dalam database PostgreSQL.
    
    PENTING: Fungsi ini membuka session database BARU (SessionLocal). 
    Jangan pernah menggunakan session DB dari HTTP request utama di sini, karena fungsi ini 
    berjalan di background task setelah HTTP request user selesai dan ditutup (closed).
    """
    try:
        from app.core.postgres import SessionLocal
        from app.services.history.history_service import HistoryService

        with SessionLocal() as db:
            HistoryService.update_ragas(
                db=db,
                history_id=history_id,
                ragas_result=result,
            )
    except Exception as exc:
        logger.error(
            "[AutoEval] Gagal update RAGAS ke DB (history_id=%s): %s",
            history_id, exc, exc_info=True,
        )