"""
UU AI Assistant — Backend Service
===================================
Entry point FastAPI application.

Services:
- /api/v1/cleaning   → PDF Cleaning Pipeline
- /api/v1/chunking   → Hierarchical Chunking Pipeline

Run:
    uvicorn main:app --reload
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.config import settings
from app.services.qdrant_service import QdrantService

__all__ = ["app"]

# ─────────────────────────────────────────────
# LOGGING SETUP
# ─────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler("logs/app.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# LIFESPAN (startup + shutdown)
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── STARTUP ──
    logger.info(f"🚀 {settings.app_name} v{settings.app_version} starting...")
    settings.ensure_dirs()

    # Cek koneksi Qdrant (non-blocking jika gagal)
    qdrant = QdrantService()
    health = qdrant.health_check()
    if health["status"] == "ok":
        logger.info(f"✅ Qdrant terhubung: {health['collections']} collection(s)")
    else:
        logger.warning(f"⚠️  Qdrant tidak tersedia: {health['detail']} (service tetap berjalan)")

    # Preload embedding model (agar request pertama tidak lambat)
    from app.services.embedding_service import EmbeddingService
    emb = EmbeddingService()
    try:
        emb.load()
        logger.info(f"✅ Embedding model siap: '{settings.embedding_model}' (dim={emb.embedding_dim})")
    except Exception as e:
        logger.warning(f"⚠️  Embedding model tidak bisa dimuat: {e} (service tetap berjalan)")

    yield  # ← app berjalan di sini

    # ── SHUTDOWN ──
    logger.info("👋 Service shutdown")



# ─────────────────────────────────────────────
# APP INIT
# ─────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    description="""
## UU AI Assistant — Data Processing Service

Service untuk memproses dokumen undang-undang Indonesia:

### Pipeline
```
PDF Upload
    ↓
[Cleaning Service]
    - Ekstraksi teks per halaman (PyMuPDF)
    - Fix encoding & unicode
    - Hapus header/footer berulang
    - Normalisasi whitespace
    ↓
[Hierarchical Chunking Service]
    - Level 0: Document (intro/header)
    - Level 1: BAB
    - Level 2: Pasal (dengan konteks BAB)
    - Level 3: Ayat (dengan konteks Pasal + BAB)
    ↓
[Qdrant Vector DB]
    - Simpan chunk + metadata
    - Siap untuk RAG retrieval
```
""",
    docs_url="/docs",
    redoc_url="/redoc",
)


# ─────────────────────────────────────────────
# MIDDLEWARE
# ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Sesuaikan untuk production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(api_router)


@app.get("/", tags=["Health"])
async def root():
    return JSONResponse({
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
    })


@app.get("/health", tags=["Health"])
async def health():
    qdrant = QdrantService()
    qdrant_status = qdrant.health_check()
    return JSONResponse({
        "status": "ok",
        "qdrant": qdrant_status,
    })
