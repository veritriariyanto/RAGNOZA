from fastapi import APIRouter
from app.routes.knowlagebase.insert_knowlagebase_routes import router as insert_knowlagebase_router

knowlagebase_router = APIRouter()

knowlagebase_router.include_router(insert_knowlagebase_router, prefix="/knowlagebase", tags=["knowlagebase"])