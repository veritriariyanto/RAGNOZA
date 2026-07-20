# app/database/models/ragas_evaluation.py

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.postgres import Base


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

    answer_qa = Column(Text, nullable=True)

    risk_faithfulness = Column(Float, nullable=True)

    # FIX : skor faithfulness per-segmen, agar skor gabungan
    # (kolom `faithfulness` di atas) tidak menyembunyikan segmen mana yang bermasalah.
    faithfulness_summary = Column(Float, nullable=True)
    faithfulness_qa = Column(Float, nullable=True)

    # FIX : simpan teks persis yang dikirim ke LLM judge untuk segmen
    # yang SEBELUMNYA TIDAK PERNAH tersimpan (kolom `answer_qa` sudah menyimpan
    # segmen QA sejak awal, jadi tidak perlu duplikat).
    faithfulness_text = Column(Text, nullable=True)   # segment_faithfulness (Summary+Clause+Reference)
    answer_risk_text = Column(Text, nullable=True)    # segment_risk

    evaluated_segments = Column(JSON, nullable=True)

    status = Column(String, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    process = relationship(
        "RAGProcess",
        back_populates="evaluations",
    )