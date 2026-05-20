# embeddings.py

from langchain_huggingface import HuggingFaceEmbeddings

# Inisialisasi Embeddings secara terpusat
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)