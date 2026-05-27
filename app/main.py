#main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# =========================================
# IMPORT ROUTERS
# =========================================
from app.routes.routes import api_router


# =========================================
# FASTAPI APP
# =========================================
app = FastAPI(
    title="RAGNOZA API",
    description="AI RAG UUD Decision Support"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Ubah sesuai kebutuhan, sebaiknya hanya domain yang diperlukan
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True
)

# =========================================
# MAIN API ROUTER (centralized)
# =========================================
app.include_router(api_router, prefix="/api/v1")

# =========================================
# ROOT
# =========================================
@app.get("/")
async def root():

    return {
        "message": "RAGNOZA API Running"
    }
