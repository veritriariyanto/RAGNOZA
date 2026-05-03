from langchain_groq import ChatGroq
from app.core.config import settings

# Inisialisasi LLM secara terpusat
llm = ChatGroq(
    temperature=0,
    groq_api_key=settings.GROQ_API_KEY, # Menggunakan Pydantic settings yang tadi
    model_name="llama-3.3-70b-versatile"
)