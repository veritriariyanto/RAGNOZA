# app/database/models/rag_process.py

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.postgres import Base


class RAGProcess(Base):
    __tablename__ = "rag_process"

    id = Column(Integer, primary_key=True, index=True)

    session_id = Column(
        Integer,
        ForeignKey("rag_session.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    raw_transcribe = Column(Text, nullable=True)
    repaired_text = Column(Text, nullable=True)
    search_query = Column(Text, nullable=True)
    retrieved_context = Column(Text, nullable=True)
    generated_material = Column(Text, nullable=True)
    compliance_score = Column(Integer, nullable=True)
    decision_status = Column(String, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    session = relationship(
        "RAGSession",
        back_populates="processes",
    )

    evaluations = relationship(
        "RAGASEvaluation",
        back_populates="process",
        cascade="all, delete-orphan",
        order_by="RAGASEvaluation.created_at",
    )


# Alias lama agar kode existing tidak rusak 
RAGHistory = RAGProcess 