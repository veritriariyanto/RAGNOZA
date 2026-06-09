from fastapi import APIRouter

from .evaluasi.ragas_router import ragas_router
from .history.history_router import router as history_router

router = APIRouter()

# ── MEMASUKKAN SUB-ROUTER HISTORY ─────────────────────────────────────────────
router.include_router(
    history_router,
    prefix="/history"
)

# ── MEMASUKKAN SUB-ROUTER RAGAS EVALUATION ────────────────────────────────────
router.include_router(
    ragas_router,
    prefix="/evaluation"
)