#app/routes/prompting/prompting_routes.py

from fastapi import APIRouter
from app.routes.prompting.audio_router import router as audio_router
from app.routes.prompting.repair_text import router as repair_text_router
from app.routes.prompting.integration_router import router as integration_router
from app.routes.prompting.generate_content_routes import router as generate_content_router

prompting_router = APIRouter()

prompting_router.include_router(audio_router, prefix="/audio", tags=["audio"])
prompting_router.include_router(repair_text_router, prefix="/repair_text", tags=["repair text"])
prompting_router.include_router(integration_router, prefix="/integration", tags=["integration"])
prompting_router.include_router(generate_content_router, prefix="/generate", tags=["generate"])
