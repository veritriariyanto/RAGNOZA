from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def health_check():
    return {
        "status": "online",
        "system": "Decision Support UUD Engine",
        "database": "Connected",
    }