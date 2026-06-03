from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from app.core.postgres import Base
from datetime import datetime

class LegalMaterialHistory(Base):
    __tablename__ = "legal_material_histories"

    # Mengikuti pattern id dari UUDArticle
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), default="Untitled Analysis")
    
    # Metadata Tracker
    status = Column(String(50))
    provider = Column(String(50), nullable=True)
    knowledge_base = Column(String(100), nullable=True)
    
    # Data Transkripsi
    transcription_raw = Column(Text, nullable=True)
    transcription_repaired = Column(Text, nullable=True)
    
    # Struktur Data Nested/Bertingkat (RAG & LLM Output)
    rag_metadata = Column(JSONB, nullable=True)          # Menampung query_used, has_context, dll.
    generated_material = Column(JSONB)                    # Menampung summary, risk_review, qa, dll.
    evaluation = Column(JSONB, nullable=True)            # Menampung status & log RAGAS
    
    # Jejak Waktu
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)