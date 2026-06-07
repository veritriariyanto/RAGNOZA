#main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# =========================================
# IMPORT ROUTERS
# =========================================
from app.routes.prompting.prompting_routes import prompting_router
from app.routes.knowlagebase.knowlagebase_routes import knowlagebase_router
from app.routes.history.history_router import router as history_router
from app.routes.evaluasi.ragas_router import ragas_router as evaluation_router


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
app.include_router(prompting_router, prefix="/api/v1/prompting")
app.include_router(knowlagebase_router, prefix="/api/v1/knowledgebase")
app.include_router(history_router, prefix="/api/v1/history")
app.include_router(evaluation_router, prefix="/api/v1/evaluation")

# =========================================
# ROOT
# =========================================
@app.get("/")
async def root():

    return {
        "message": "RAGNOZA API Running"
    }
