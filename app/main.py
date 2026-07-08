#main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# =========================================
# IMPORT ROUTERS
# =========================================
from app.routes.prompting.prompting_routes import prompting_router
from app.routes.knowlagebase.knowlagebase_routes import knowlagebase_router
from app.routes.history.history_router import router as history_router
from app.routes.evaluation.evaluation_router import router as evaluation_router
from app.routes.evaluation.evaluation_dataset_router import router as evaluation_dataset_router

# =========================================
# SWAGGER TAG DEFINITIONS
# =========================================
tags_metadata = [
    {
        "name": "📄 Chunking Pipeline",
        "description": (
            "**Pipeline utama pemrosesan dokumen hukum.** "
            "Upload PDF → Cleaning (ekstrak & bersihkan teks) → "
            "Chunking hierarki Parent-Child (Konsiderans, Batang Tubuh per-Pasal, Penjelasan). "
            "Gunakan endpoint **[3] Chunking JSON** untuk mendapat hasil chunk siap pakai."
        ),
    },
    {
        "name": "📦 Knowledge Base - Management",
        "description": (
            "Manajemen Knowledge Base di Qdrant: ingest dokumen, lihat statistik, "
            "hapus koleksi, dan listing collections yang tersedia."
        ),
    },
    {
        "name": "🔍 Knowledge Base - Search",
        "description": "Pencarian semantik pada Knowledge Base yang telah di-ingest ke Qdrant.",
    },
    {
        "name": "prompting",
        "description": "Endpoint RAG prompting — tanya jawab berbasis dokumen UU.",
    },
    {
        "name": "history",
        "description": "Riwayat sesi dan percakapan.",
    },
    {
        "name": "evaluation",
        "description": "Evaluasi kualitas retrieval menggunakan RAGAS.",
    },
]

# =========================================
# FASTAPI APP
# =========================================
app = FastAPI(
    title="RAGNOZA API",
    description=(
        "**RAG-based Legal Document AI Assistant**\n\n"
        "Pipeline pemrosesan dokumen hukum Indonesia (UU, PP, Perpres) berbasis "
        "Parent-Child Chunking + Qdrant vector database.\n\n"
        "### Alur Utama\n"
        "1. Upload PDF via **📄 Chunking Pipeline → [1] Upload & Cleaning**\n"
        "2. Proses chunking via **[2] Cleaning → Chunking**\n"
        "3. Dapatkan array JSON chunks via **[3] Chunking JSON**\n"
        "4. Index ke Qdrant via **📦 Knowledge Base - Management → /ingest**\n"
        "5. Cari via **🔍 Knowledge Base - Search**"
    ),
    version="1.0.0",
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Ubah sesuai kebutuhan, sebaiknya hanya domain yang diperlukan
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True
)

# =========================================
# MAIN API ROUTER (centralized)
# =========================================
app.include_router(knowlagebase_router, prefix="/api/v1/knowledgebase")
app.include_router(prompting_router, prefix="/api/v1/prompting")
app.include_router(history_router, prefix="/api/v1/history")
app.include_router(evaluation_router, prefix="/api/v1/evaluation")
app.include_router(evaluation_dataset_router, prefix="/api/v1/evaluation-dataset", tags=["evaluation"])

# =========================================
# ROOT
# =========================================
@app.get("/", tags=["root"])
async def root():

    return {
        "message": "RAGNOZA API Running",
        "docs": "/docs",
        "version": "1.0.0",
    }
