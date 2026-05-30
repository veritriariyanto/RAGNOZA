"""
evaluator/app/core/config.py

Konfigurasi untuk evaluator service.
Hanya berisi settings yang dibutuhkan oleh RAGAS dan LLM evaluator.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class EvaluatorSettings(BaseSettings):
    # LLM untuk RAGAS evaluator
    GROQ_API_KEY: str = ""
    evaluator_llm_model: str = "llama-3.1-8b-instant"
    evaluator_llm_temperature: float = 0.0

    # Embedding untuk RAGAS
    evaluator_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    evaluator_embedding_device: str = "cpu"

    # Logging
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