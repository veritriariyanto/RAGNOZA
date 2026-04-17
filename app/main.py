from fastapi import FastAPI, Depends, Form,UploadFile, File
from sqlalchemy.orm import Session
from app.database.postgres import get_db, engine, Base
from app.database.qdrant import qdrant_db  # Import manager Qdrant kita
from app.services.rag_logic import llm
from app.models.uud import UUDArticle
from app.services.ingestion import run_ingestion_upload
from app.services.ask_service import get_answer_from_rag

# Create tables in Postgres (Laragon) if they don't exist
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI RAG UUD Decision Support")

@app.on_event("startup")
async def startup_event():
    """
    Event ini berjalan saat server dimulai.
    Memastikan koleksi di Qdrant sudah dibuat sebelum ada request masuk.
    """
    try:
        # Inisialisasi koleksi Qdrant (384 sesuai dimensi all-MiniLM-L6-v2)
        qdrant_db.init_collection(collection_name="uud_articles", vector_size=384)
        print("✅ Berhasil memvalidasi koneksi PostgreSQL dan Qdrant.")
    except Exception as e:
        print(f"❌ Terjadi kesalahan saat startup: {e}")

@app.get("/")
async def health_check():
    return {
        "status": "online", 
        "system": "Decision Support UUD Engine",
        "database": "Connected"
    }

@app.post("/ingest")
async def ingest_document(
    collection_name: str = Form(...), # User menginput nama koleksi via form
    file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    # 1. Validasi format file
    if not file.filename.endswith('.pdf'):
        return {"error": "Hanya file PDF yang diperbolehkan"}
    
    # 2. Baca isi file menjadi bytes
    contents = await file.read()
    
    # 3. Panggil service dengan menyertakan nama koleksi
    result = run_ingestion_upload(contents, db, collection_name)
    
    return result

@app.get("/collections")
async def list_collections():
    """Melihat daftar knowledge base yang sudah di-ingest"""
    from app.database.qdrant import qdrant_db
    collections = qdrant_db.client.get_collections().collections
    return {"available_collections": [c.name for c in collections]}

@app.post("/ask")
async def ask_question(
    prompt: str, 
    collection_name: str # User WAJIB memasukkan nama koleksi di sini
):
    """
    Endpoint ini memungkinkan user memilih collection mana 
    yang ingin dijadikan sumber pengetahuan.
    """
    try:
        # Data 'collection_name' dari user diteruskan ke service
        result = get_answer_from_rag(prompt, collection_name)
        return result
    except Exception as e:
        return {"error": f"Gagal mengambil data dari koleksi {collection_name}: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    # Menggunakan port 8000 sebagai standar FastAPI
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)