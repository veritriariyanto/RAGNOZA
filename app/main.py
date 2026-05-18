"""
UU AI Assistant — Backend Service
===================================
Entry point FastAPI application.

Services:
- /api/v1/cleaning   → PDF Cleaning Pipeline
- /api/v1/chunking   → Hierarchical Chunking Pipeline
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
# pyrefly: ignore [missing-import]
from loguru import logger
import sys

from app.api.v1.router import api_router
from app.config import settings
from app.services.qdrant_service import QdrantService

__all__ = ["app"]

# ─────────────────────────────────────────────
# LOGGING SETUP
# ─────────────────────────────────────────────
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>",
    level=settings.log_level,
    colorize=True,
)
logger.add(
    "logs/app.log",
    rotation="10 MB",
    retention="7 days",
    level="INFO",
)


# ─────────────────────────────────────────────
# APP INIT
# ─────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
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


# ─────────────────────────────────────────────
# EVENTS
# ─────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    logger.info(f"🚀 {settings.app_name} v{settings.app_version} starting...")
    settings.ensure_dirs()

    # Cek koneksi Qdrant (non-blocking jika gagal)
    qdrant = QdrantService()
    health = qdrant.health_check()
    if health["status"] == "ok":
        logger.success(f"✅ Qdrant terhubung: {health}")
    else:
        logger.warning(f"⚠️  Qdrant tidak tersedia: {health['detail']} (service tetap berjalan)")


@app.on_event("shutdown")
async def shutdown():
    logger.info("👋 Service shutdown")


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────
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