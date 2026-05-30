"""
evaluator/main.py

Service evaluator RAGAS — berjalan di port 8001 secara terpisah dari service utama.
Dipanggil oleh service utama (port 8000) via HTTP POST /evaluate sebagai background task.

Isolasi dependency:
    - Service ini menggunakan ragas + langchain 0.3.x
    - Service utama (8000) menggunakan langchain 1.3.x
    - Keduanya TIDAK bisa berada dalam satu venv yang sama
"""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.evaluation_router import router as evaluation_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Evaluator service starting on port 8001")
    logger.info("📦 RAGAS evaluation service ready")
    yield
    logger.info("🛑 Evaluator service shutting down")


app = FastAPI(
    title="RAGNOZA Evaluator Service",
    description="Service evaluasi RAGAS — dijalankan terpisah dari service utama",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://app:8000"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

app.include_router(evaluation_router, prefix="/api/v1", tags=["evaluation"])


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "evaluator", "port": 8001}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)