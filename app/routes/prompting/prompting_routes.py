from fastapi import APIRouter
from app.routes.prompting.audio_router import router as audio_router
from app.routes.prompting.rag_router import router as rag_router

prompting_router = APIRouter()

# Di sini audio didaftarkan ke prompting
prompting_router.include_router(audio_router, prefix="/audio", tags=["Audio"])

# Di sini RAG didaftarkan ke prompting
prompting_router.include_router(rag_router, tags=["RAG"])
