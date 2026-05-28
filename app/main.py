#main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# =========================================
# IMPORT ROUTERS
# =========================================
from app.routes.prompting.prompting_routes import prompting_router
from app.routes.knowlagebase.knowlagebase_routes import knowlagebase_router
from app.routes.history_routes import api_router
from app.routes.evaluation_router import router as evaluation_router


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
# MAIN API ROUTER
# =========================================
app.include_router(prompting_router, prefix="/api/v1")
app.include_router(knowlagebase_router, prefix="/api/v1")
app.include_router(api_router, prefix="/api/v1")
app.include_router(evaluation_router, prefix="/api/v1")

# =========================================
# ROOT
# =========================================
@app.get("/")
async def root():

    return {
        "message": "RAGNOZA API Running"
    }