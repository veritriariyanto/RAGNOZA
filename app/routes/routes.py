from fastapi import APIRouter
from app.routes.prompting.prompting_routes import prompting_router
from app.routes.knowlagebase.knowlagebase_routes import knowlagebase_router

api_router = APIRouter()

# Di sini prompting didaftarkan ke main (v1)
api_router.include_router(prompting_router, prefix="/prompting")
api_router.include_router(knowlagebase_router, prefix="/knowlagebase")