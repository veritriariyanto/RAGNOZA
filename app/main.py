from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.routes.routes import api_router
from app.routes.prompting.rag_router import router as rag_router

app = FastAPI(title="RAGNOZA API")

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── STATIC FILES ───────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
app.mount("/js",     StaticFiles(directory="frontend/js"),     name="js")

# ── API ROUTERS ────────────────────────────────────────────────────────────────
app.include_router(api_router, prefix="/api/v1")
app.include_router(rag_router)

# ── FRONTEND ───────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return FileResponse("frontend/index.html")