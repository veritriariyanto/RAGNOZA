"""
evaluator/app/core/config.py

Konfigurasi untuk evaluator service.
Hanya berisi settings yang dibutuhkan oleh RAGAS dan LLM evaluator.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class EvaluatorSettings(BaseSettings):
    GROQ_API_KEY: str = "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"
    
    # Model untuk RAG pipeline (generate jawaban)
    evaluator_llm_model: str = "llama-3.1-8b-instant"
    evaluator_llm_temperature: float = 0.0

    # ← TAMBAH: Model terpisah khusus untuk RAGAS evaluator
    ragas_llm_model: str = "llama-3.3-70b-versatile"  # model lebih besar, masih gratis di Groq
    ragas_llm_temperature: float = 0.0

    evaluator_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    evaluator_embedding_device: str = "cpu"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> EvaluatorSettings:
    return EvaluatorSettings()


settings = get_settings()