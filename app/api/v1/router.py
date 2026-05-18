"""
app/api/v1/router.py
=====================
Aggregates all v1 endpoint routers.
"""

from fastapi import APIRouter
from app.api.v1.endpoints import cleaning, chunking

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(cleaning.router)
api_router.include_router(chunking.router)
