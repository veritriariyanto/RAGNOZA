#app/core/llm_provider.py

from langchain_groq import ChatGroq
from app.core.config import settings

# Inisialisasi LLM secara terpusat
llm = ChatGroq(
    temperature=0.1,
    groq_api_key=settings.GROQ_API_KEY, # Menggunakan Pydantic settings yang tadi
    model_name="llama-3.1-8b-instant",
    max_retries=5,
    request_timeout=60,
)