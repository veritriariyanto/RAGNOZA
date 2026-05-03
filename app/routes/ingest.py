from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.postgres import get_db
from app.services.ingestion import run_ingestion_upload

router = APIRouter()


@router.post("/ingest")
async def ingest_document(
    collection_name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename.endswith(".pdf"):
        return {"error": "Hanya file PDF yang diperbolehkan"}

    contents = await file.read()
    return run_ingestion_upload(contents, db, collection_name)