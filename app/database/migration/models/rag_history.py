# app/database/migration/models/rag_history.py

from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func

from app.core.postgres import Base

class RAGHistory(Base): 
    __tablename__ = "rag_history"

    id = Column(Integer, primary_key=True, index=True)

    knowledge_base = Column(String, nullable=True)
    provider = Column(String, nullable=True)

    raw_transcribe = Column(Text, nullable=True)
    repaired_text = Column(Text, nullable=True)

    search_query = Column(Text, nullable=True)

    retrieved_context = Column(Text, nullable=True)

    generate_material = Column(Text, nullable=True)

    compliance_score = Column(Integer, nullable=True)

    decision_status = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())