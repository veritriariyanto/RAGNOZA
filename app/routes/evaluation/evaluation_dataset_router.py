# app/routes/evaluation/evaluation_dataset_router.py

import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
import io
import pandas as pd
from fastapi import UploadFile, File

from app.core.postgres import get_db, SessionLocal
from app.database.models.evaluation_dataset import (
    EvaluationDataset,
    EvaluationDatasetItem,
    EvaluationRun,
    EvaluationRunItemResult,
)
from app.database.models.rag_process import RAGProcess
from app.database.models.ragas_evaluation import RAGASEvaluation
from app.schemas.evaluation.evaluation_dataset import (
    EvaluationDatasetCreate,
    EvaluationDatasetResponse,
    EvaluationDatasetItemBulkCreate,
    EvaluationDatasetItemResponse,
    EvaluationRunTriggerRequest,
    EvaluationRunResponse,
    EvaluationRunReportResponse,
    EvaluationRunItemDetail,
)
from app.services.evaluation.dataset_runner_service import run_dataset_evaluation
from app.services.prompting.audio.stt_service import STTService
from app.services.prompting.prompt.repair_text import TextRefinerService
from app.services.prompting.prompt.generate_content_service import MaterialGeneratorService
from app.services.knowlagebase.qdrant_service import QdrantService
from app.services.prompting.integration.rag_integration_service import RAGIntegrationService
from app.schemas.evaluation.evaluation_dataset import CsvUploadResult, CsvUploadRowError
from app.services.knowlagebase.qdrant_service import QdrantService

logger = logging.getLogger(__name__)
router = APIRouter()

REQUIRED_CSV_COLUMNS = {"question", "ground_truth", "reference_context", "knowledge_base"}
OPTIONAL_CSV_COLUMNS = {"category"}

@router.get("/csv-template")
def download_csv_template():
    """
    Unduh template CSV kosong dengan header kolom yang benar,
    supaya tim non-teknis tahu persis format yang diharapkan.
    """
    from fastapi.responses import StreamingResponse

    header = "question,ground_truth,reference_context,category,knowledge_base\n"
    example = (
        '"Contoh pertanyaan hukum di sini",'
        '"Contoh jawaban rujukan di sini",'
        '"Kutip persis teks pasal di sini",'
        '"kategori_opsional",'
        '"nama_collection_qdrant"\n'
    )
    buffer = io.StringIO(header + example)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=template_dataset_evaluasi.csv"},
    )


@router.post("/{dataset_id}/items/upload-csv", response_model=CsvUploadResult)
async def upload_items_csv(
    dataset_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload CSV berisi banyak soal sekaligus untuk golden dataset.

    Kolom wajib: question, ground_truth, reference_context, knowledge_base
    Kolom opsional: category

    Validasi per baris:
    - Semua kolom wajib tidak boleh kosong
    - knowledge_base harus cocok dengan collection yang benar-benar ada di Qdrant
      (dicek via QdrantService.list_collections() — reuse, bukan logic baru)

    Baris yang gagal validasi dilewati (tidak menggagalkan seluruh upload),
    dan dilaporkan di response agar tim non-teknis tahu baris mana yang perlu diperbaiki.
    """
    dataset = db.query(EvaluationDataset).filter(EvaluationDataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset tidak ditemukan")

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "File harus berformat .csv")

    raw_bytes = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw_bytes), dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except Exception as exc:
        raise HTTPException(400, f"Gagal membaca file CSV: {exc}")

    missing_columns = REQUIRED_CSV_COLUMNS - set(df.columns)
    if missing_columns:
        raise HTTPException(
            400,
            f"Kolom wajib berikut tidak ditemukan di CSV: {', '.join(sorted(missing_columns))}. "
            f"Unduh template terlebih dahulu via GET /evaluation-dataset/csv-template",
        )

    # Reuse QdrantService.list_collections() yang sudah ada — validasi nama KB benar-benar eksis
    qdrant = QdrantService()
    valid_kb_names = set(await qdrant.list_collections())

    errors: list[CsvUploadRowError] = []
    valid_items: list[EvaluationDatasetItem] = []

    for idx, row in df.iterrows():
        row_num = idx + 2  # +2: header row + 1-based index, biar cocok dengan nomor baris di Excel/Sheets

        question = row.get("question", "").strip()
        ground_truth = row.get("ground_truth", "").strip()
        reference_context = row.get("reference_context", "").strip()
        knowledge_base = row.get("knowledge_base", "").strip()
        category = row.get("category", "").strip() or None

        if not question or not ground_truth or not reference_context or not knowledge_base:
            errors.append(CsvUploadRowError(
                row_number=row_num,
                reason="Ada kolom wajib yang kosong (question/ground_truth/reference_context/knowledge_base)",
            ))
            continue

        if knowledge_base not in valid_kb_names:
            errors.append(CsvUploadRowError(
                row_number=row_num,
                reason=(
                    f"knowledge_base '{knowledge_base}' tidak ditemukan di Qdrant. "
                    f"Collection yang tersedia: {', '.join(sorted(valid_kb_names)) or '(tidak ada)'}"
                ),
            ))
            continue

        valid_items.append(EvaluationDatasetItem(
            dataset_id=dataset.id,
            question=question,
            ground_truth=ground_truth,
            reference_context=reference_context,
            category=category,
            knowledge_base=knowledge_base,
        ))

    if valid_items:
        db.add_all(valid_items)
        db.commit()

    return CsvUploadResult(
        dataset_id=dataset.id,
        inserted_count=len(valid_items),
        skipped_count=len(errors),
        errors=errors,
    )

# ── Dataset CRUD ─────────────────────────────────────────────────────────

@router.post("/", response_model=EvaluationDatasetResponse)
def create_dataset(payload: EvaluationDatasetCreate, db: Session = Depends(get_db)):
    dataset = EvaluationDataset(name=payload.name, description=payload.description)
    db.add(dataset)
    try:
        db.commit()
        db.refresh(dataset)
    except Exception as exc:
        db.rollback()
        raise HTTPException(400, f"Gagal membuat dataset (nama mungkin sudah dipakai): {exc}")

    return EvaluationDatasetResponse(
        id=dataset.id, name=dataset.name, description=dataset.description,
        total_items=0, created_at=dataset.created_at,
    )


@router.get("/", response_model=list[EvaluationDatasetResponse])
def list_datasets(db: Session = Depends(get_db)):
    datasets = db.query(EvaluationDataset).order_by(EvaluationDataset.created_at.desc()).all()
    return [
        EvaluationDatasetResponse(
            id=d.id, name=d.name, description=d.description,
            total_items=len(d.items), created_at=d.created_at,
        )
        for d in datasets
    ]


@router.post("/{dataset_id}/items", response_model=list[EvaluationDatasetItemResponse])
def add_items(dataset_id: int, payload: EvaluationDatasetItemBulkCreate, db: Session = Depends(get_db)):
    dataset = db.query(EvaluationDataset).filter(EvaluationDataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset tidak ditemukan")

    created = []
    for item_in in payload.items:
        item = EvaluationDatasetItem(
            dataset_id=dataset.id,
            question=item_in.question,
            ground_truth=item_in.ground_truth,
            reference_context=item_in.reference_context,
            category=item_in.category,
        )
        db.add(item)
        created.append(item)

    db.commit()
    for item in created:
        db.refresh(item)

    return [EvaluationDatasetItemResponse.model_validate(i) for i in created]


@router.get("/{dataset_id}/items", response_model=list[EvaluationDatasetItemResponse])
def list_items(dataset_id: int, db: Session = Depends(get_db)):
    dataset = db.query(EvaluationDataset).filter(EvaluationDataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset tidak ditemukan")
    return [EvaluationDatasetItemResponse.model_validate(i) for i in dataset.items]


# ── Trigger Run ──────────────────────────────────────────────────────────

async def _run_dataset_background(dataset_id: int, label: str | None):
    """
    Wrapper background task — membuka SessionLocal BARU (bukan session request),
    mengikuti pola yang sama seperti evaluation_db_service.update_ragas_in_db().
    """
    with SessionLocal() as db:
        stt = STTService()
        refiner = TextRefinerService()
        material_gen = MaterialGeneratorService()
        qdrant = QdrantService()
        rag_service = RAGIntegrationService(
            stt_service=stt,
            text_service=refiner,
            vector_service=qdrant,
            material_service=material_gen,
            db=db,
        )
        await run_dataset_evaluation(db=db, dataset_id=dataset_id, rag_service=rag_service, label=label)


@router.post("/{dataset_id}/run", response_model=EvaluationRunResponse)
def trigger_run(
    dataset_id: int,
    payload: EvaluationRunTriggerRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    dataset = db.query(EvaluationDataset).filter(EvaluationDataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset tidak ditemukan")
    if not dataset.items:
        raise HTTPException(400, "Dataset belum punya item — tambahkan soal terlebih dahulu")

    # Buat baris run status "pending" di request thread agar run_id bisa langsung dikembalikan
    run = EvaluationRun(dataset_id=dataset.id, label=payload.label, status="pending")
    db.add(run)
    db.commit()
    db.refresh(run)

    background_tasks.add_task(_run_dataset_background, dataset_id, payload.label)

    logger.info(
        "[DatasetRouter] Run trigger diterima — dataset_id=%d | run_id_placeholder=%d",
        dataset_id, run.id,
    )

    return EvaluationRunResponse.model_validate(run)

@router.get("/{dataset_id}/runs", response_model=list[EvaluationRunResponse])
def list_runs(dataset_id: int, db: Session = Depends(get_db)):
    """
    Daftar semua run (riwayat) untuk satu dataset, terbaru lebih dulu.
    Dibutuhkan agar UI bisa menampilkan pilihan run tanpa user harus
    mengetahui/mencatat run_id secara manual.
    """
    dataset = db.query(EvaluationDataset).filter(EvaluationDataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset tidak ditemukan")

    runs = (
        db.query(EvaluationRun)
        .filter(EvaluationRun.dataset_id == dataset_id)
        .order_by(EvaluationRun.triggered_at.desc())
        .all()
    )
    return [EvaluationRunResponse.model_validate(r) for r in runs]

@router.get("/runs/{run_id}", response_model=EvaluationRunReportResponse)
def get_run_report(run_id: int, db: Session = Depends(get_db)):
    run = db.query(EvaluationRun).filter(EvaluationRun.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run tidak ditemukan")

    results = db.query(EvaluationRunItemResult).filter(EvaluationRunItemResult.run_id == run.id).all()

    items_detail: list[EvaluationRunItemDetail] = []
    live_scores, ref_scores = [], []
    by_category: dict[str, list] = {}

    for r in results:
        item = r.dataset_item
        if r.process_id is None:
            continue

        evaluations = (
            db.query(RAGASEvaluation)
            .filter(RAGASEvaluation.process_id == r.process_id)
            .filter(RAGASEvaluation.evaluation_type.in_(["dataset_eval_live", "dataset_eval_reference"]))
            .all()
        )

        for ev in evaluations:
            detail = EvaluationRunItemDetail(
                dataset_item_id=item.id,
                question=item.question,
                category=item.category,
                process_id=r.process_id,
                evaluation_type=ev.evaluation_type,
                faithfulness_summary=ev.faithfulness_summary,
                faithfulness_qa=ev.faithfulness_qa,
                answer_relevancy=ev.answer_relevancy,
                context_precision=ev.context_precision,
                context_recall=ev.context_recall,
                risk_faithfulness=ev.risk_faithfulness,
            )
            items_detail.append(detail)

            bucket = live_scores if ev.evaluation_type == "dataset_eval_live" else ref_scores
            bucket.append(ev)

            if item.category:
                by_category.setdefault(item.category, []).append(ev)

    def _avg(evals: list, field: str) -> float | None:
        vals = [getattr(e, field) for e in evals if getattr(e, field) is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    metric_fields = [
        "faithfulness_summary", "faithfulness_qa", "answer_relevancy",
        "context_precision", "context_recall", "risk_faithfulness",
    ]

    aggregate_live = {f: _avg(live_scores, f) for f in metric_fields}
    aggregate_reference = {f: _avg(ref_scores, f) for f in metric_fields}
    aggregate_by_category = {
        cat: {f: _avg(evals, f) for f in metric_fields}
        for cat, evals in by_category.items()
    }

    return EvaluationRunReportResponse(
        run_id=run.id,
        dataset_id=run.dataset_id,
        label=run.label,
        status=run.status,
        total_items=len(results),
        aggregate_live=aggregate_live,
        aggregate_reference=aggregate_reference,
        aggregate_by_category=aggregate_by_category,
        items=items_detail,
    )