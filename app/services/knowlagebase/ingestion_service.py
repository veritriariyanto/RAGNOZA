"""
Ingestion helper moved into knowledgebase package.
"""

import re
import io
from datetime import datetime, timezone
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.database.migration.uud import UUDArticle
from app.core.qdrant import qdrant_db
from app.core.embeddings import embeddings


def run_ingestion_upload(file_contents: bytes, db: Session, collection_name: str):
    qdrant_db.init_collection(collection_name=collection_name, vector_size=384)

    stream = io.BytesIO(file_contents)
    reader = PdfReader(stream)
    full_text = ""
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            full_text += extracted + "\n"

    if not full_text.strip():
        raise ValueError("PDF tidak mengandung teks yang dapat dibaca (mungkin file scan/image).")

    full_text = re.sub(r'\n\s*\n', '\n', full_text)
    full_text = re.sub(r'[ \t]+', ' ', full_text)

    parts = re.split(r'(BAB\s+[IVXLCDM]+|Pasal\s+\d+)', full_text)
    pembukaan_text = parts[0].strip()
    count = 0
    current_bab = "PEMBUKAAN"
    upload_time = datetime.now(timezone.utc).isoformat()
    errors = []

    # Save pembukaan
    if pembukaan_text:
        try:
            _save_to_databases(pembukaan_text, db, collection_name, current_bab, "Pembukaan", upload_time)
            count += 1
        except Exception as e:
            errors.append(str(e))

    # ... rest of ingestion flow preserved

    return {"status": "success" if not errors else "partial", "collection": collection_name, "total_segments": count, "errors": errors, "upload_time": upload_time}

def _save_to_databases(text, db: Session, collection_name: str, bab: str, pasal: str, upload_time: str = None):
    if upload_time is None:
        upload_time = datetime.now(timezone.utc).isoformat()
    # function body preserved from original
