#app/routes/api_router.py

from fastapi import APIRouter

from .history.history_router import router as history_router
from .evaluation.evaluation_router import router as evaluation_router
from .evaluation.evaluation_dataset_router import router as evaluation_dataset_router   # ← BARU

router = APIRouter()

# ── MEMASUKKAN SUB-ROUTER HISTORY ─────────────────────────────────────────────
router.include_router(
    history_router,
    prefix="/history"
)

# ── MEMASUKKAN SUB-ROUTER RAGAS EVALUATION ────────────────────────────────────
router.include_router(
    evaluation_router,
    prefix="/evaluation"
)

# ── MEMASUKKAN SUB-ROUTER DATASET EVALUATION (Fase 1) ─────────────────────────
router.include_router(
    evaluation_dataset_router,
    prefix="/evaluation-dataset"
)