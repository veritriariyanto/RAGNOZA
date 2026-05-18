"""
app/config.py
=============
Central settings for the application.
Reads values from environment variables / .env file.
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Literal


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────
    app_name: str = "UU AI Assistant"
    app_version: str = "1.0.0"
    log_level: str = "INFO"

    # ── Database ─────────────────────────────────
    pghost: str = "localhost"
    pgport: int = 5432
    pgdatabase: str = "ragdb"
    pguser: str = "postgres"
    pgpassword: str = ""
    pgsslmode: str = "disable"
    database_url: str = "postgresql://postgres@localhost:5432/ragdb"

    # ── Vector DB ────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    # ── AI / Groq ────────────────────────────────
    groq_api_key: str = ""

    # ── Cleaning pipeline flags ───────────────────
    cleaning_fix_encoding: bool = True
    cleaning_remove_header_footer: bool = True
    cleaning_normalize_whitespace: bool = True

    # ── Chunking token limits ─────────────────────
    chunk_level_1_max_tokens: int = 1500
    chunk_level_2_max_tokens: int = 800
    chunk_level_3_max_tokens: int = 300
    chunk_overlap_tokens: int = 50
    chunk_min_tokens: int = 5

    # ── Embedding ─────────────────────────────────────────────────
    # Model multilingual ringan, mendukung Bahasa Indonesia (384 dim)
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    embedding_device: str = "cpu"       # "cpu" | "cuda" | "mps"
    embedding_batch_size: int = 32
    # Collection terpisah: parent = konteks, child = vector search
    embedding_collection_parent: str = "uu_chunks_parent"
    embedding_collection_child: str = "uu_chunks_child"

    # ── Output dirs ───────────────────────────────
    output_dir: str = "app/output"
    logs_dir: str = "logs"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore unknown env vars
    )

    def ensure_dirs(self):
        """Create required output directories if they don't exist."""
        for d in [self.output_dir, self.logs_dir]:
            os.makedirs(d, exist_ok=True)


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
