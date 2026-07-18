# app/core/config.py

"""Canonical application settings.

This module defines the single `settings` object used across the codebase.
Other modules may import `from app.core.config import settings` to access
configuration. `app.config` will act as a lightweight shim for backwards
compatibility.
"""

import os
from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────
    app_name: str = "UU AI Assistant"
    app_version: str = "1.0.0"
    log_level: str = "INFO"

    # ── Database ─────────────────────────────────
    PGHOST: str = "localhost"
    PGPORT: int = 5432
    PGDATABASE: str = "ragnoza_db"
    PGUSER: str = "postgres"
    PGPASSWORD: str = "ragnoza123"
    PGSSLMODE: str = "disable"

    @property
    def database_url(self) -> str:
        auth = self.PGUSER
        if self.PGPASSWORD:
            auth += f":{self.PGPASSWORD}"

        return (
            f"postgresql://{auth}"
            f"@{self.PGHOST}:{self.PGPORT}/{self.PGDATABASE}"
        )

    @property
    def DATABASE_URL(self) -> str:
        return self.database_url

    # ── Vector DB ────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    # ── OpenRouter LLM / API keys ────────────────
    openrouter_api_key: str = ""
    cleaning_llm_model: str = ""
    cleaning_llm_temperature: float = 0.1
    cleaning_llm_concurrency: int = 2

    # Backwards-compatible API key names commonly used in .env
    GROQ_API_KEY: str = ""
    ELEVENLABS_API_KEY: str = ""

    # ── Chunking token limits ─────────────────────
    chunk_level_1_max_tokens: int = 1500
    chunk_level_2_max_tokens: int = 800
    chunk_level_3_max_tokens: int = 300
    chunk_overlap_tokens: int = 50
    chunk_min_tokens: int = 5

    # ── Embedding ─────────────────────────────────
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    embedding_device: str = "cpu"
    embedding_batch_size: int = 32
    embedding_collection_parent: str = "uu_chunks_parent"
    embedding_collection_child: str = "uu_chunks_child"

    # ── Output dirs ───────────────────────────────
    output_dir: str = "app/output"
    logs_dir: str = "logs"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def ensure_dirs(self):
        for d in [self.output_dir, self.logs_dir]:
            os.makedirs(d, exist_ok=True)


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
