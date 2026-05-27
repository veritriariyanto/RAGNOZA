#app/routes/knowlagebase/search_knowlagebase_routes.py

from fastapi import APIRouter, Form, HTTPException
from app.services.knowledgebase.kb_service import kb_service
from app.services.knowledgebase.qdrant_service import QdrantService
from fastapi.responses import JSONResponse

router = APIRouter()

@router.post("/search/{base_name}")
async def search_kb(
    base_name: str,
    query: str = Form(...),
    section_type: str = Form(None),
    pasal_type: str = Form(None),
    limit: int = Form(5)
):
    try:
        # ✅ Cukup panggil service, tidak perlu tahu implementasi di bawahnya
        result = await kb_service.search_knowledgebase(
            base_name=base_name,
            query=query,
            section_type=section_type,
            pasal_type=pasal_type,
            limit=limit
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal melakukan pencarian: {str(e)}")


@router.get("/collections")
async def list_qdrant_collections():
    try:
        qdrant = QdrantService()
        detailed = qdrant.get_collections_detailed()
        return JSONResponse(content=detailed)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal mengambil collections dari Qdrant: {str(e)}")