from fastapi import APIRouter

from .evaluasi.ragas_router import ragas_router
from .history.history_router import router as history_router

router = APIRouter()

router.include_router(
    history_router,
    prefix="/history"
)

router.include_router(
    ragas_router,
    prefix="/evaluation"
)