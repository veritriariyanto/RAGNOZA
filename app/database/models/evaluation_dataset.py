# app/database/models/evaluation_dataset.py

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.postgres import Base


class EvaluationDataset(Base):
    """
    Definisi satu koleksi soal uji (golden dataset) untuk Dataset Evaluation.
    Independen dari histori interaksi user riil (RAGSession/RAGProcess).
    """
    __tablename__ = "evaluation_dataset"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    items = relationship(
        "EvaluationDatasetItem",
        back_populates="dataset",
        cascade="all, delete-orphan",
    )
    runs = relationship(
        "EvaluationRun",
        back_populates="dataset",
        cascade="all, delete-orphan",
    )


class EvaluationDatasetItem(Base):
    """
    Satu soal kurasi di dalam golden dataset.
    reference_context dikunci manual agar skor benchmark reproducible
    meski isi Qdrant berubah seiring waktu.
    """
    __tablename__ = "evaluation_dataset_item"

    id = Column(Integer, primary_key=True, index=True)

    dataset_id = Column(
        Integer,
        ForeignKey("evaluation_dataset.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    question = Column(Text, nullable=False)
    ground_truth = Column(Text, nullable=False)
    reference_context = Column(Text, nullable=False)
    category = Column(String(100), nullable=True, index=True)
    knowledge_base = Column(String(100), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    dataset = relationship(
        "EvaluationDataset",
        back_populates="items",
    )
    run_results = relationship(
        "EvaluationRunItemResult",
        back_populates="dataset_item",
        cascade="all, delete-orphan",
    )


class EvaluationRun(Base):
    """
    Satu kali eksekusi penuh atas dataset tertentu.
    Mendukung perbandingan skor antar-waktu (mis. sebelum/sesudah ganti prompt).
    """
    __tablename__ = "evaluation_run"

    id = Column(Integer, primary_key=True, index=True)

    dataset_id = Column(
        Integer,
        ForeignKey("evaluation_dataset.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    label = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default="pending")
    notes = Column(Text, nullable=True)

    triggered_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    dataset = relationship(
        "EvaluationDataset",
        back_populates="runs",
    )
    item_results = relationship(
        "EvaluationRunItemResult",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class EvaluationRunItemResult(Base):
    """
    Penaut murni antara satu item dataset, satu run, dan hasil eksekusinya
    di RAGProcess. TIDAK menyimpan skor sendiri — skor tetap satu-satunya
    sumber kebenaran di RAGASEvaluation (via relasi RAGProcess.evaluations),
    dibedakan lewat evaluation_type ('dataset_eval_live' / 'dataset_eval_reference').
    """
    __tablename__ = "evaluation_run_item_result"

    id = Column(Integer, primary_key=True, index=True)

    run_id = Column(
        Integer,
        ForeignKey("evaluation_run.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_item_id = Column(
        Integer,
        ForeignKey("evaluation_dataset_item.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    process_id = Column(
        Integer,
        ForeignKey("rag_process.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    run = relationship(
        "EvaluationRun",
        back_populates="item_results",
    )
    dataset_item = relationship(
        "EvaluationDatasetItem",
        back_populates="run_results",
    )