"""
app/services/evaluation/dataset_runner_service.py

FASE 1 — Dataset Evaluation (golden dataset, kurasi manual).

Menjalankan satu EvaluationRun: iterasi setiap EvaluationDatasetItem,
reuse penuh pipeline RAG (RAGIntegrationService.process_text_to_material)
dan mesin evaluasi RAGAS yang sudah ada (trigger_auto_evaluation) —
tidak ada logic RAG/evaluasi baru di file ini.

Setiap item menghasilkan 1x generate material, dievaluasi 2x:
  - "dataset_eval_live"      : context dari retrieval Qdrant live (apa adanya)
  - "dataset_eval_reference" : context dikunci manual dari kurasi soal (reproducible)
Keduanya tersimpan sebagai baris terpisah di RAGASEvaluation, menunjuk ke
process_id yang sama (1 material, 2 penilaian context berbeda).
"""

import logging

from sqlalchemy.orm import Session

from app.database.models.evaluation_dataset import (
    EvaluationDataset,
    EvaluationDatasetItem,
    EvaluationRun,
    EvaluationRunItemResult,
)
from app.services.evaluation.evaluation_hook import trigger_auto_evaluation
from app.services.prompting.integration.rag_integration_service import RAGIntegrationService
from app.services.prompting.prompt.generate_content_service import SYSTEM_ERROR_FALLBACK_MESSAGE

logger = logging.getLogger(__name__)

async def run_dataset_evaluation(
    db: Session,
    dataset_id: int,
    rag_service: RAGIntegrationService,
    label: str | None = None,
) -> dict:
    """
    Entry-point utama Fase 1. Dijalankan sebagai background task oleh router
    (durasinya bisa panjang — sama seperti pertimbangan throttle Groq yang
    sudah ada di alur eval biasa).
    """
    dataset = db.query(EvaluationDataset).filter(EvaluationDataset.id == dataset_id).first()
    if not dataset:
        logger.warning("[DatasetRunner] dataset_id=%d tidak ditemukan", dataset_id)
        return {"status": "error", "error": "Dataset tidak ditemukan"}

    items = list(dataset.items)
    if not items:
        logger.warning("[DatasetRunner] dataset_id=%d tidak punya item", dataset_id)
        return {"status": "error", "error": "Dataset kosong, tidak ada item untuk dievaluasi"}

    run = EvaluationRun(dataset_id=dataset.id, label=label, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)

    logger.info(
        "[DatasetRunner] Mulai run_id=%d untuk dataset_id=%d ('%s') | %d item",
        run.id, dataset.id, dataset.name, len(items),
    )

    success_count = 0
    failed_count = 0

    for item in items:
        try:
            result = await run_single_item(db, rag_service, item)
            db.add(EvaluationRunItemResult(
                run_id=run.id,
                dataset_item_id=item.id,
                process_id=result.get("process_id"),
            ))
            db.commit()
            success_count += 1
        except Exception as exc:
            logger.error(
                "[DatasetRunner] Gagal eval item_id=%d (run_id=%d): %s",
                item.id, run.id, exc, exc_info=True,
            )
            # Tetap catat baris hasil meski gagal, process_id=None,
            # agar item yang gagal tetap terlihat di laporan run.
            db.add(EvaluationRunItemResult(
                run_id=run.id,
                dataset_item_id=item.id,
                process_id=None,
            ))
            db.commit()
            failed_count += 1

    from datetime import datetime, timezone
    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(
        "[DatasetRunner] Selesai run_id=%d | sukses=%d | gagal=%d",
        run.id, success_count, failed_count,
    )

    return {
        "status": "success",
        "run_id": run.id,
        "total_items": len(items),
        "success_count": success_count,
        "failed_count": failed_count,
    }


async def run_single_item(
    db: Session,
    rag_service: RAGIntegrationService,
    item: EvaluationDatasetItem,
) -> dict:
    """
    Eksekusi 1 item dataset:
      1. Jalankan pipeline penuh (repair→search→generate) via process_text_to_material,
         ground_truth diisi dari item → auto eval "live" otomatis terpicu di dalamnya
         (source_label="dataset_eval_live"), termasuk precision/recall karena
         ground_truth sudah tersedia.
      2. Panggil trigger_auto_evaluation KEDUA KALINYA dengan context dikunci
         dari item.reference_context → source_label="dataset_eval_reference".
    """
    # 1. Eksekusi pipeline + eval "live" (reuse penuh, tidak ada logic baru)
    rag_result = await rag_service.process_text_to_material(
        raw_text=item.question,
        knowledge_base=item.knowledge_base,
        auto_evaluate=True,
        ground_truth=item.ground_truth,
        is_dataset_eval=True,
    )

    process_id = rag_result.history_id
    final_material = rag_result.final_material

    if not final_material or process_id is None:
        raise RuntimeError(
            f"Pipeline gagal menghasilkan material untuk item_id={item.id} "
            f"(kemungkinan tidak ada context relevan ditemukan di KB)"
        )

    # ▼▼▼ BLOK PENGGANTI ADA DI SINI ▼▼▼
    is_system_error = bool(
        final_material.ringkasan
        and final_material.ringkasan[0].poin == SYSTEM_ERROR_FALLBACK_MESSAGE
    )
    if is_system_error:
        raise RuntimeError(
            f"Generate gagal (SYSTEM_ERROR) untuk item_id={item.id} — "
            f"dilewati dari evaluasi RAGAS, bukan kegagalan retrieval."
        )
    # ▲▲▲ BLOK PENGGANTI SAMPAI SINI ▲▲▲

    # 2. Eval kedua: context dikunci manual dari kurasi soal (reproducible benchmark)
    reference_chunks = [
        c.strip() for c in item.reference_context.split("\n\n") if c.strip()
    ] or [item.reference_context]

    await trigger_auto_evaluation(
        question=item.question,
        context=item.reference_context,
        material=final_material,
        ground_truth=item.ground_truth,
        source_label="dataset_eval_reference",
        history_id=process_id,
        context_chunks=reference_chunks,
    )

    return {"process_id": process_id}