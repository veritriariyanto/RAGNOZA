from fastapi import APIRouter

from app.routes.ask import router as ask_router
from app.routes.collections import router as collections_router
from app.routes.health import router as health_router
from app.routes.ingest import router as ingest_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(ingest_router)
api_router.include_router(collections_router)
api_router.include_router(ask_router)