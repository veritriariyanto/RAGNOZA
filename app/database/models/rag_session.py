# app/database/models/rag_session.py

from sqlalchemy import Column, DateTime, Integer, String
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