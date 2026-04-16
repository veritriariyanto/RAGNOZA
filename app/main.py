from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from app.database.postgres import get_db, engine, Base
from app.services.rag_logic import llm

# Create tables in Postgres if they don't exist
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI RAG UUD")

@app.get("/")
async def health_check():
    return {"status": "online", "system": "Decision Support UUD Engine"}

@app.post("/ask")
async def ask_question(prompt: str, db: Session = Depends(get_db)):
    # Placeholder: Nanti kita tambahkan logika similarity search Qdrant di sini
    response = llm.invoke(prompt)
    return {"question": prompt, "answer": response.content}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)