# File: RAGNOZA/app/routes/knowlagebase/knowlagebase_routes.py

from fastapi import APIRouter
from app.routes.knowlagebase.insert_knowlagebase_routes import router as insert_knowlagebase_router
from app.routes.knowlagebase.search_knowlagebase_routes import router as search_knowlagebase_router

knowlagebase_router = APIRouter()

# ── Qdrant Insert & Delete (KB Management) ─────────────────────────────────────
knowlagebase_router.include_router(
    insert_knowlagebase_router,
    prefix="/qdran",
    tags=["📦 Knowledge Base - Management"],
)

# ── Qdrant Search ───────────────────────────────────────────────────────────────
knowlagebase_router.include_router(
    search_knowlagebase_router,
    prefix="/qdran",
    tags=["🔍 Knowledge Base - Search"],
)

# ── Chunking Pipeline (Cleaning → Chunking → Embedding) ───────────────────────
# Re-include insert_router with /chunking prefix so the pipeline endpoints
# (/upload, /process, /process/chunks) appear grouped separately in Swagger.
from fastapi import APIRouter as _AR
_chunking_router = _AR()

from app.routes.knowlagebase.insert_knowlagebase_routes import (
    upload_and_clean,
    process_pdf,
    process_and_get_chunks,
)

_chunking_router.add_api_route(
    "/upload",
    upload_and_clean,
    methods=["POST"],
    summary="[1] Upload & Cleaning – Ekstrak & bersihkan teks PDF",
    description=(
        "Upload file PDF undang-undang. Pipeline akan mengekstrak teks "
        "mentah dari setiap halaman, membersihkan artefak PDF (ligature, "
        "page number, header/footer berulang), normalisasi unicode, dan "
        "mengembalikan statistik cleaning."
    ),
)
_chunking_router.add_api_route(
    "/process",
    process_pdf,
    methods=["POST"],
    summary="[2] Cleaning → Chunking – Proses penuh + statistik",
    description=(
        "Upload PDF → cleaning → chunking hierarki parent-child. "
        "Gunakan **include_chunks_preview=true** untuk melihat preview 20 chunk pertama. "
        "Gunakan **include_raw_chunks=true** untuk mendapat seluruh array chunk dalam response. "
        "Gunakan **embed=true** untuk langsung meng-embed dan index ke Qdrant."
    ),
)
_chunking_router.add_api_route(
    "/process/chunks",
    process_and_get_chunks,
    methods=["POST"],
    summary="[3] Chunking JSON – Kembalikan array parent-child chunks",
    description=(
        "Upload PDF → cleaning → chunking → kembalikan **array JSON lengkap** "
        "berisi semua parent dan child chunks. Format output identik dengan "
        "`uu_2_2002_full_parent_child_chunks.json` (contoh di folder document). "
        "Cocok untuk debugging dan validasi hasil chunking."
    ),
    response_description="Array JSON berisi parent-child chunks",
)

knowlagebase_router.include_router(
    _chunking_router,
    prefix="/chunking",
    tags=["📄 Chunking Pipeline"],
)