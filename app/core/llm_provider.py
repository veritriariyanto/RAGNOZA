#app/core/llm_provider.py

from langchain_groq import ChatGroq
from app.core.config import settings

# Inisialisasi LLM secara terpusat
llm = ChatGroq(
    temperature=0.1,
    groq_api_key=settings.GROQ_API_KEY, # Menggunakan Pydantic settings yang tadi
    model_name="openai/gpt-oss-20b",
    max_retries=5,
    request_timeout=60,
)