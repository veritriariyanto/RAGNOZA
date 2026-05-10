from fastapi import APIRouter
from app.routes.prompting.audio_router import router as audio_router
from app.routes.prompting.repair_text import router as repair_text_router

prompting_router = APIRouter()

prompting_router.include_router(audio_router, prefix="/audio", tags=["audio"])
prompting_router.include_router(repair_text_router, prefix="/repair_text", tags=["repair_text"])