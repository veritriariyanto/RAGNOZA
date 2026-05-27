#app/routes/routes.py

from fastapi import APIRouter

# Import sub-routers
from app.routes.prompting.prompting_routes import prompting_router
from app.routes.knowlagebase.knowlagebase_routes import knowlagebase_router
from app.routes.evaluasi import router as evaluasi_router

api_router = APIRouter()

# Centralized router registration
# Prompting endpoints (will be available under /api/v1/audio, /api/v1/integration, etc.)
api_router.include_router(prompting_router)

# Knowledgebase (Qdrant) endpoints — knowlagebase_router already defines its own sub-prefix (/qdran)
api_router.include_router(knowlagebase_router)

# Evaluasi package (history, evaluation, ...)
api_router.include_router(evaluasi_router, prefix="/evaluasi")
