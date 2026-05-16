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
    title="RAGNOZA API"
)

# =========================================
# CORS
# =========================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================
# MAIN API ROUTER
# =========================================
app.include_router(
    api_router,
    prefix="/api/v1"
)

# =========================================
# ROOT
# =========================================
@app.get("/")
async def root():

    return {
        "message": "RAGNOZA API Running"
    }