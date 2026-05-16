#app/routes/routes.py

from fastapi import APIRouter
from app.routes.prompting.prompting_routes import prompting_router
from app.routes.kb_router import router as kb_router

api_router = APIRouter()

# Di sini prompting didaftarkan ke main (v1)
api_router.include_router(prompting_router, prefix="/prompting")


# Knowledge Base (upload PDF, list, delete)
api_router.include_router(kb_router, prefix="/kb", tags=["Knowledge Base"])
