from fastapi import APIRouter, HTTPException, status, Depends
from app.schemas.prompting.generate_content import MaterialRequest, MaterialResponse
from app.services.prompting.prompt.generate_content_service import material_service

router = APIRouter()

@router.post(
    "/generate", 
    response_model=MaterialResponse, 
    status_code=status.HTTP_200_OK,
    summary="Generate Legal Material"
)
async def create_material(payload: MaterialRequest):
    """
    Endpoint untuk membuat materi edukasi hukum berbasis teks/konteks tertentu.
    """
    try:
        result = await material_service.generate_legal_material(payload)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gagal generate material: {str(e)}"
        )