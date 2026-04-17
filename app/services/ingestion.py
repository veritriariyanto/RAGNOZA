import re
import io
from pypdf import PdfReader
from sqlalchemy.orm import Session
from app.models.uud import UUDArticle
from app.database.qdrant import qdrant_db
from app.services.rag_logic import embeddings

def run_ingestion_upload(file_contents: bytes, db: Session, collection_name: str):
    # 1. Pastikan koleksi target sudah ada di Qdrant
    # Dimensi 384 sesuai dengan model all-MiniLM-L6-v2
    qdrant_db.init_collection(collection_name=collection_name, vector_size=384)

    stream = io.BytesIO(file_contents)
    reader = PdfReader(stream)
    
    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text() + "\n"

    # Bersihkan teks dari baris kosong berlebih
    full_text = re.sub(r'\n\s*\n', '\n', full_text)

    # Regex untuk membagi berdasarkan BAB dan Pasal
    parts = re.split(r'(BAB\s+[IVXLCDM]+|Pasal\s+\d+)', full_text)
    
    pembukaan_text = parts[0].strip()
    count = 0
    current_bab = "PEMBUKAAN"

    # Simpan bagian Pembukaan
    if pembukaan_text:
        _save_to_databases(current_bab, "Pembukaan", pembukaan_text, db, collection_name)
        count += 1

    # Proses bagian lainnya
    for i in range(1, len(parts), 2):
        header = parts[i].strip()
        content = parts[i+1].strip() if (i+1) < len(parts) else ""

        if header.startswith("BAB"):
            # Update konteks BAB saat ini (ambil judul bab di baris pertama)
            lines = content.split('\n', 1)
            current_bab = f"{header} {lines[0].strip()}"
            continue

        if header.startswith("Pasal"):
            # Gabungkan konteks agar AI lebih paham saat retrieval
            full_context = f"[{current_bab}] {header}: {content}"
            _save_to_databases(current_bab, header, full_context, db, collection_name)
            count += 1
        
    return {
        "status": "success",
        "collection": collection_name,
        "total_segments": count
    }

def _save_to_databases(bab, pasal, text, db: Session, collection_name: str):
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
                "isi_teks": text
            }
        }]
    )