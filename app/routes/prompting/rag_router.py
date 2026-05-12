from fastapi import APIRouter
from pydantic import BaseModel

from app.services.ask_service import get_answer_from_rag

router = APIRouter()

class RagRequest(BaseModel): 
    prompt: str
    collection_name: str

@router.post("/rag/ask")
async def ask_question(request: RagRequest):
    result = get_answer_from_rag(
        request.prompt,
        request.collection_name
    )

    return result
