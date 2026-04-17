import os
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from dotenv import load_dotenv

load_dotenv()

# 1. Inisialisasi Embeddings (untuk mengubah prompt jadi vektor)
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

# 2. Inisialisasi LLM Groq
llm = ChatGroq(
    temperature=0, # 0 agar jawaban faktual sesuai teks UUD
    groq_api_key=os.getenv("GROQ_API_KEY"),
    model_name="llama-3.3-70b-versatile" # Model terbaru sesuai permintaan
)