#ingestion.py

import re
import io
from datetime import datetime, timezone
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.database.migration.uud import UUDArticle
from app.core.qdrant import qdrant_db
from app.core.embeddings import embeddings

def run_ingestion_upload(file_contents: bytes, db: Session, collection_name: str):
    """
    Parse PDF, chunk per Pasal/Bab, lalu simpan ke PostgreSQL + Qdrant.
 
    Returns:
        dict: status, collection, total_segments
    """

    # 1. Pastikan koleksi target sudah ada di Qdrant
    # Dimensi 384 sesuai dengan model all-MiniLM-L6-v2
    qdrant_db.init_collection(collection_name=collection_name, vector_size=384)

    #2. Ekstrak teks dari PDF
    stream = io.BytesIO(file_contents)
    reader = PdfReader(stream)
    
    full_text = ""
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            full_text += extracted + "\n"
    
    if not full_text.strip():
        raise ValueError("PDF tidak mengandung teks yang dapat dibaca (mungkin file scan/image).")
    

    # Bersihkan teks dari baris kosong berlebih
    full_text = re.sub(r'\n\s*\n', '\n', full_text)
    full_text = re.sub(r'[ \t]+', ' ', full_text)

    # Regex untuk membagi berdasarkan BAB dan Pasal / Split berdasarkan BAB dan pasal
    parts = re.split(r'(BAB\s+[IVXLCDM]+|Pasal\s+\d+)', full_text)
    
    pembukaan_text = parts[0].strip()
    count = 0
    current_bab = "PEMBUKAAN"
    upload_time = datetime.now(timezone.utc).isoformat()
    errors = []

    # Simpan bagian Pembukaan
    if pembukaan_text:
        try:
            _save_to_databases(
                bab=current_bab, 
                pasal="Pembukaan", 
                isi_teks=pembukaan_text, 
                db=db, 
                collection_name=collection_name,
                upload_time=upload_time
            )
            count += 1
        except Exception as e:
            errors.append(f"Error menyimpan Pembukaan: {str(e)}")

    # Proses bagian lainnya / BAB dan Pasal
    for i in range(1, len(parts), 2):
        header = parts[i].strip()
        content = parts[i+1].strip() if (i+1) < len(parts) else ""

        if header.startswith("BAB"):
            # Update konteks BAB saat ini (ambil judul bab di baris pertama)
            lines = content.split('\n', 1)
            current_bab = f"{header} {lines[0].strip()}"
            continue

        if header.startswith("Pasal"):
            if not content:
                continue # Skip pasal kosong
            # Gabungkan konteks agar AI lebih paham saat retrieval
            full_context = f"[{current_bab}] {header}: {content}"

            try:
                _save_to_databases(
                    bab=current_bab, 
                    pasal=header,
                    text=full_context,
                    db=db,
                    collection_name=collection_name,
                    upload_time=upload_time
                )
                count += 1
            except Exception as e:
                errors.append(f"Error menyimpan {header}: {str(e)}")
             
    return {
        "status": "success" if not errors else "partial",
        "collection": collection_name,
        "total_segments": count,
        "errors": errors,
        "upload_time": upload_time
    }

def _save_to_databases(
        bab: str,   
        pasal: str, 
        text: str, 
        db: Session, 
        collection_name: str,
        upload_time: str = None
):
    """
    Simpan satu segmen ke PostgreSQL dan Qdrant.
    Cek duplikat berdasarkan (bab, pasal) sebelum menyimpan.
    """
    if upload_time is None:
        upload_time = datetime.now(timezone.utc).isoformat()

    #Cek duplikat di PostgreSQL
    existing = db.query(UUDArticle).filter(
        UUDArticle.bab == bab,
        UUDArticle.pasal == pasal
    ).first()

    if existing:
        #Update sisi teks jika sudah ada (re-upload)
        existing.isi_teks = text
        db.commit()
        db.refresh(existing)
        article_id = existing.id

        #Update vector di Qdrant
        vector = embeddings.embed_query(text)
        qdrant_db.client.upsert(
            collection_name=collection_name,
            points=[{
                "id": article_id,
                "vector": vector,
                "payload": {
                    "bab": bab,
                    "pasal": pasal,
                    "isi_teks": text,
                    "upload_time": upload_time
            }
            }]
        )
        return

    # 1. Simpan ke PostgreSQL (Ground Truth)
    new_entry = UUDArticle(
        bab=bab,
        pasal=pasal, 
        isi_teks=text
    )
    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)

    # 2. Simpan ke Qdrant (Vector Store)
    vector = embeddings.embed_query(text)
    qdrant_db.client.upsert(
        collection_name=collection_name,
        points=[{
            "id": new_entry.id, 
            "vector": vector, 
            "payload": {
                "bab": bab,
                "pasal": pasal, 
                "isi_teks": text,
                "upload_time": upload_time
            }
        }]
    )