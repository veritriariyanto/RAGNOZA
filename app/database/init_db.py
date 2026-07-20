# app/database/init_db.py
import logging
from app.core.postgres import engine, Base

# ===========================================================================
# CRITICAL STEP: Kamu WAJIB meng-import semua model di sini.
# Jika tidak di-import, SQLAlchemy tidak akan tahu bahwa tabel ini eksis!
# ===========================================================================
# CATATAN: LegalMaterialHistory (app.database.migration.history) DIHAPUS dari sini —
# model tersebut & RAGHistoryService sudah tidak dipakai jalur manapun yang aktif
# (jalur history yang aktif sekarang: RAGProcess + SessionService). Lihat audit
# Fase 0 RAGAS untuk detail.

# FASE 1 — Dataset Evaluation (golden dataset, independen dari histori user riil)
from app.database.models.evaluation_dataset import (
    EvaluationDataset,
    EvaluationDatasetItem,
    EvaluationRun,
    EvaluationRunItemResult,
)

# Setup logging sederhana
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    try:
        logger.info("Menghubungkan ke PostgreSQL dan mendeteksi skema...")
        Base.metadata.create_all(bind=engine)
        logger.info("Selamat! Semua tabel berhasil dibuat/diperbarui tanpa Alembic.")
    except Exception as e:
        logger.error(f"Gagal menjalankan migrasi: {str(e)}")

if __name__ == "__main__":
    run_migration()