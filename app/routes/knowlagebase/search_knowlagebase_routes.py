#app/routes/knowlagebase/search_knowlagebase_routes.py

from fastapi import APIRouter, Form, HTTPException
from app.services.knowlagebase.kb_service import kb_service
from fastapi.responses import JSONResponse

router = APIRouter()

@router.post("/search/{base_name}")
async def search_kb(
    base_name: str,
    query: str = Form(...),
    section_type: str = Form(None),
    pasal_type: str = Form(None),
    limit: int = Form(5),
    score_threshold: float = Form(0.15),
):
    try:
        result = await kb_service.search_knowledgebase(
            base_name=base_name,
            query=query,
            section_type=section_type,
            pasal_type=pasal_type,
            limit=limit,
            score_threshold=score_threshold,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal melakukan pencarian: {str(e)}")
