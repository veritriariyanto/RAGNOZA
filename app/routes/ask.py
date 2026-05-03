from fastapi import APIRouter

from app.services.ask_service import get_answer_from_rag

router = APIRouter()


@router.post("/ask")
async def ask_question(
    prompt: str,
    collection_name: str,
):
    """
    Endpoint ini memungkinkan user memilih collection mana
    yang ingin dijadikan sumber pengetahuan.
    """
    try:
        return get_answer_from_rag(prompt, collection_name)
    except Exception as e:
        return {"error": f"Gagal mengambil data dari koleksi {collection_name}: {str(e)}"}