from langchain_groq import ChatGroq
from langchain_community.embeddings import HuggingFaceEmbeddings
import os

# Model Llama 3 70B dari Groq
llm = ChatGroq(
    model_name="llama3-70b-8192",
    groq_api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.1 # Rendah agar jawaban lebih faktual sesuai UUD
)

# Embedding lokal (Efisien dan akurat untuk teks Indonesia)
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")