# app/core/embeddings.py

from langchain_huggingface import HuggingFaceEmbeddings

# Model multilingual — mendukung 50+ bahasa termasuk Bahasa Indonesia
# Dimensi output: 384 (sama dengan all-MiniLM-L6-v2 → Qdrant collections tidak perlu dibuat ulang)
# Namun KB yang sudah ada WAJIB di-ingest ulang karena embedding space berbeda.
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)