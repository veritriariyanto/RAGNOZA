"""Evaluation routes package entrypoint.

This file exposes a single `router` that aggregates all evaluation-related
sub-routers (history, evaluation, etc.). Import this one router from
`app.routes.evaluasi` in your central `routes.py`.
"""

from fastapi import APIRouter

from ..history.history_router import router as history_router
from .evaluation_router import router as evaluation_router

router = APIRouter()

# Mount history under /history
router.include_router(history_router, prefix="/history", tags=["History"])

# Mount evaluation endpoints under / (or choose a sub-prefix if desired)
router.include_router(evaluation_router, prefix="", tags=["Evaluasi"])

__all__ = ["router"]
