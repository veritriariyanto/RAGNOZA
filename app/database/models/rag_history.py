# app/database/models/rag_history.py

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.postgres import Base


class RAGSession(Base):
    __tablename__ = "rag_session"

    id = Column(Integer, primary_key=True, index=True)
    session_title = Column(String, nullable=True)
    knowledge_base = Column(String, nullable=True)
    provider = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    processes = relationship(
        "RAGProcess",
        back_populates="session",
        cascade="all, delete-orphan",
    )


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
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("RAGSession", back_populates="processes")
    evaluations = relationship(
        "RAGASEvaluation",
        back_populates="process",
        cascade="all, delete-orphan",
        order_by="RAGASEvaluation.created_at",
    )


class RAGASEvaluation(Base):
    __tablename__ = "ragas_evaluation"

    id = Column(Integer, primary_key=True, index=True)
    process_id = Column(
        Integer,
        ForeignKey("rag_process.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evaluation_type = Column(String, nullable=True)
    question = Column(Text, nullable=True)
    answer = Column(Text, nullable=True)
    ground_truth = Column(Text, nullable=True)
    faithfulness = Column(Float, nullable=True)
    answer_relevancy = Column(Float, nullable=True)
    context_precision = Column(Float, nullable=True)
    context_recall = Column(Float, nullable=True)
    overall_score = Column(Float, nullable=True)
    status = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    process = relationship("RAGProcess", back_populates="evaluations")


# Compatibility alias for existing imports while the rest of the codebase is migrated.
RAGHistory = RAGProcess