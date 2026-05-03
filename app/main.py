from fastapi import FastAPI
from app.core.postgres import engine, Base
from app.core.qdrant import qdrant_db
from app.routes import api_router

# Create tables in Postgres (Laragon) if they don't exist
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI RAG UUD Decision Support")
app.include_router(api_router)

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

if __name__ == "__main__":
    import uvicorn
    # Menggunakan port 8000 sebagai standar FastAPI
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)