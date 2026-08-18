"""
evaluator/app/core/config.py

Konfigurasi untuk evaluator service.
Membaca environment variables dari file .env secara aman menggunakan Pydantic.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class EvaluatorSettings(BaseSettings):
    # API Keys (Tanpa nilai default, Pydantic akan error jika variabel ini tidak ada di .env)
    GROQ_API_KEY: str
    ELEVENLABS_API_KEY: str  # Ditambahkan agar siap digunakan jika dibutuhkan oleh service lain

    # Model untuk RAG pipeline (generate jawaban)
    EVALUATOR_LLM_MODEL: str = "openai/gpt-oss-20b"
    EVALUATOR_LLM_TEMPERATURE: float = 0.0

    # Model terpisah khusus untuk RAGAS evaluator
    RAGAS_LLM_MODEL: str = "openai/gpt-oss-120b"
    RAGAS_LLM_TEMPERATURE: float = 0.0

    # Konfigurasi Embedding & Sistem
    EVALUATOR_EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EVALUATOR_EMBEDDING_DEVICE: str = "cpu"
    LOG_LEVEL: str = "INFO"

    # ← TAMBAH: Konfigurasi Throttling
    GROQ_TPM_LIMIT: int = 4500
    GROQ_MIN_GAP_SEC: float = 1.2
    GROQ_TPD_LIMIT: int = 90000  # buffer di bawah TPD riil — sesuaikan per dashboard Groq Anda
    GROQ_RPD_LIMIT: int = 1000  # buffer di bawah RPD riil — sesuaikan per dashboard Groq


    # Konfigurasi Pydantic untuk membaca file .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Mengabaikan variabel lain di .env yang tidak didefinisikan di class ini
    )

#Fungsi @lru_cache() di bagian bawah memastikan bahwa proses pembacaan konfigurasi ini hanya dilakukan sekali (singleton pattern), 
#sehingga menghemat memori dan meningkatkan performa saat modul lain memanggil settings
@lru_cache()
def get_settings() -> EvaluatorSettings:
    return EvaluatorSettings()


# Instance singleton untuk di-import oleh file/modul lain
settings = get_settings()