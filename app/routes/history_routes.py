#app/routes/routes.py

from fastapi import APIRouter
from app.routes.prompting.prompting_routes import prompting_router
from app.routes.knowlagebase.knowlagebase_routes import knowlagebase_router
from app.routes.history_router import router as history_router

api_router = APIRouter()

# Di sini prompting didaftarkan ke main (v1)
api_router.include_router(history_router, prefix="/history", tags=["History"])
