"""
Endpoint routes migrated from app/api/v1/endpoints/similarity.py
"""

import os
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from app.services.qdrant_service import QdrantService

router = APIRouter(prefix="/api/v1/similarity", tags=["Similarity Testing"])
logger = logging.getLogger(__name__)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.abspath(os.path.join(CURRENT_DIR, "..", "templates", "similarity_test.html"))


@router.get("/ui", response_class=HTMLResponse, summary="Tampilkan dashboard UI similarity test")
async def get_similarity_ui():
    if not os.path.exists(TEMPLATE_PATH):
        logger.error(f"HTML Template tidak ditemukan di: {TEMPLATE_PATH}")
        raise HTTPException(status_code=404, detail=f"UI template not found at {TEMPLATE_PATH}")
    try:
        with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content, status_code=200)
    except Exception as e:
        logger.error(f"Gagal membaca HTML Template: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read UI template: {str(e)}")


@router.get("/collections", summary="Dapatkan statistik detail collections di Qdrant")
async def get_collections_stats():
    try:
        qdrant = QdrantService()
        detailed_stats = qdrant.get_collections_detailed()
        return JSONResponse(content=detailed_stats)
    except Exception as e:
        logger.error(f"Gagal mengambil statistik Qdrant: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
