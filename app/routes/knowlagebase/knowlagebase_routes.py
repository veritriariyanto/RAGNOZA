# File: RAGNOZA/app/routes/knowlagebase/knowlagebase_routes.py

from fastapi import APIRouter
from app.routes.knowlagebase.insert_knowlagebase_routes import router as insert_knowlagebase_router
from app.routes.knowlagebase.search_knowlagebase_routes import router as search_knowlagebase_router

knowlagebase_router = APIRouter()

# Panggil satu per satu
knowlagebase_router.include_router(insert_knowlagebase_router, prefix="/qdran", tags=["insert_knowledgebase"])
knowlagebase_router.include_router(search_knowlagebase_router, prefix="/qdran", tags=["search_knowledgebase"])