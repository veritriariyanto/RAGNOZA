# app/database/init_db.py
import logging
from app.core.postgres import engine, Base

# ===========================================================================
# CRITICAL STEP: Kamu WAJIB meng-import semua model di sini.
# Jika tidak di-import, SQLAlchemy tidak akan tahu bahwa tabel ini eksis!
# ===========================================================================
from app.database.migration.history import LegalMaterialHistory
# Tambahkan import model lain jika ada, contoh:
# from app.database.migration.uud import UUDArticle 

# Setup logging sederhana
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    try:
        logger.info("Menghubungkan ke PostgreSQL dan mendeteksi skema...")
        
        # Perintah sakti untuk membuat semua tabel yang belum ada di database
        Base.metadata.create_all(bind=engine)
        
        logger.info("Selamat! Semua tabel berhasil dibuat/diperbarui tanpa Alembic.")
    except Exception as e:
        logger.error(f"Gagal menjalankan migrasi: {str(e)}")

if __name__ == "__main__":
    run_migration()