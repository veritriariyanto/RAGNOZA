# app/routes/evaluation/evaluation_router.py
#
# FIX #3: tambah endpoint /ragas-reeval
#   - Dipanggil ketika user input ground_truth di Streamlit
#   - Ambil existing metrics dari DB via ProcessQueryService
#   - Kirim ke evaluator dengan is_reeval=True
#   - Evaluator hanya hitung precision+recall, merge dengan existing
#
# Tiga path tetap terisolasi — tidak ada yang memanggil satu sama lain.

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
 
from app.core.postgres import get_db
from app.schemas.evaluation.evaluation_schemas import (   # ← fix: folder baru
    EvaluationInput,
    MaterialEvaluationRequest,
    ReevalRequest,
    EvaluationResponse,
)
from app.schemas.prompting.generate_content import MaterialResponse
from app.services.evaluation.formatter import material_to_text, extract_segments_for_ragas
from app.services.evaluation.evaluation_client import call_evaluator  # ← reuse, hapus duplikasi
from app.services.history.history_service import HistoryService        # ← fix: class baru
from app.services.history.process_query_service import ProcessQueryService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Evaluation"])

def _build_payload_from_material(
    question: str, 
    context: str, 
    material: MaterialResponse,
    ground_truth, 
    source_label: str,
    context_chunks: Optional[list[str]] = None,
    
) -> dict:
    """
    Fungsi Helper Sinkron (Synchronous) untuk menyusun dan menstandarisasi 
    struktur data (payload) sebelum dikirim ke mesin penilai RAGAS.
    Fungsi ini khusus digunakan pada evaluasi pertama kali (Auto-Eval / Path A).

    Args:
        question (str): Pertanyaan asli dari user.
        context (str): Dokumen referensi yang ditarik dari database/knowledge base.
        material (MaterialResponse): Objek skema Pydantic berisi hasil generate AI (QA, Ringkasan, Risiko).
        ground_truth (any): Kunci jawaban ideal dari manusia (bisa None jika belum diisi).
        source_label (str): Penanda asal request (contoh: "frontend_eval").

    Returns:
        dict: Struktur data JSON-ready yang dipahami oleh API Evaluator.
    """
    
    # Memanggil modul formatter eksternal untuk memecah objek MaterialResponse yang kompleks 
    # menjadi potongan teks spesifik (segmentasi) berdasarkan metrik targetnya masing-masing.
    segments = extract_segments_for_ragas(material)

    # TAMBAHKAN LOG DI SINI
    logger.info(
        "[PayloadCheckRouter] question='%s' | faithfulness_text_len=%d | answer_qa='%s'",
        question[:100],
        len(segments.get("faithfulness", "")),
        segments.get("qa", "")[:200],
    )

    # Menyusun kamus data (dictionary) sesuai dengan kontrak API yang diminta oleh service Evaluator :8001
    return {
        "question": question,
        "context": context,

        #Mengubah keseluruhan objek materi (skema Pydantic) menjadi satu teks utuh (string) untuk jawaban umum
        "answer": material_to_text(material),
        # Segmen evaluasi
        "faithfulness_text": segments["faithfulness"],
        "answer_qa": segments["qa"],
        "answer_risk": segments["risk"],

        "ground_truth": ground_truth,
        "source_label": source_label,
        "context_chunks": context_chunks or [],   # ← tambah ini
        # Karena ini jalur 'Auto-Eval' pertama kali, flag 'is_reeval' diset False.
        "is_reeval": False,
    }

# =============================================================================
# ENDPOINT 1: /ragas-auto-2metriks — Path A (auto eval dari Streamlit)
# =============================================================================

@router.post("/ragas-auto-2metriks", response_model=EvaluationResponse)
async def evaluate_ragas_auto_2metrics(
    payload: MaterialEvaluationRequest,
    db: Session = Depends(get_db),
):
    # ← TAMBAH INI SEBAGAI BARIS PERTAMA
    logger.info(
        "[EvalRouter] Payload diterima | question='%s' | history_id=%s",
        payload.question[:100] if payload.question else "KOSONG",
        payload.history_id,
    )
    
    """Auto eval: terima MaterialResponse, ekstrak segmen, kirim ke evaluator."""
    try:
        material = MaterialResponse.model_validate(payload.material)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Gagal parse MaterialResponse: {exc}")

    evaluator_payload = _build_payload_from_material(
        question=payload.question,
        context=payload.context,
        material=material,
        ground_truth=payload.ground_truth,
        source_label=payload.source_label or "frontend_eval",
        context_chunks=payload.context_chunks,   # FIX: sebelumnya tidak pernah diteruskan
                                                   # → context_precision/recall selalu pakai
                                                   # fallback paragraph-split, bukan chunk retrieval asli
    )

    # =============================================================================
    # 🛑 PROTEKSI & GUARDRAIL VALIDASI INPUT (TAMBAHKAN DI SINI)
    # =============================================================================
    q_text = evaluator_payload.get("question", "").strip()
    faith_text = evaluator_payload.get("faithfulness_text", "").strip()

    # Siapkan skema input untuk audit log di frontend walaupun statusnya skipped
    fallback_input = EvaluationInput(
        question=payload.question or "-",
        context=payload.context or "-",
        answer=evaluator_payload.get("answer", "-"),
        ground_truth=payload.ground_truth,
        answer_qa=evaluator_payload.get("answer_qa", "-"),
        source_label=payload.source_label or "frontend_eval"
    )

    # 1. Deteksi jika question kosong dari Whisper atau diisi teks default template
    if not q_text or q_text in ["-", "NONE", "null"]:
        logger.warning("[EvalRouter] 🛑 Evaluasi dilewati: 'question' kosong atau tidak valid.")
        return EvaluationResponse(
            status="skipped",
            metrics=None,
            input=fallback_input,
            error="User question is empty or invalid from pipeline."
        )

    # 2. Deteksi jika text pendukung evaluasi kosong (kasus ANSWER hanya berisi "-")
    if not faith_text or faith_text == "-":
        logger.warning("[EvalRouter] 🛑 Evaluasi dilewati: Segmen jawaban kosong/hanya template strip.")
        return EvaluationResponse(
            status="skipped",
            metrics=None,
            input=fallback_input,
            error="Evaluated segments (answer) are empty or blank templates."
        )
    # =============================================================================

    # =============================================================================

    try:
        # Jika lolos validasi di atas, baru microservice evaluator (Groq/Ragas) ditembak
        result = await call_evaluator(evaluator_payload, source_label="frontend_eval")
        
        # Pastikan result tidak None sebelum di-get
        if not result or result.get("status") == "error":
            error_msg = result.get("error") if result else "Response dari evaluator kosong"
            logger.error(f"[EvalRouter] Evaluator gagal: {error_msg}")
            raise HTTPException(status_code=500, detail=f"Evaluasi gagal: {error_msg}")

        if payload.history_id is not None:
            try:
                HistoryService.update_ragas(db=db, history_id=payload.history_id, ragas_result=result)
            except Exception as db_exc:
                # Log error DB tapi jangan gagalkan return agar user tetap dapat hasil
                logger.error(f"[EvalRouter] Gagal menyimpan hasil Ragas ke DB: {db_exc}")
                # Optional: tetap lanjut karena evaluasinya sendiri sebenarnya sukses
        
        return result

    except HTTPException as http_exc:
        raise http_exc
    except Exception as general_exc:
        logger.exception("[EvalRouter] Terjadi unhandled exception di endpoint evaluasi")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(general_exc)}")

# =============================================================================
# ENDPOINT 2: /ragas-ground-truth — Path B (user input ground truth)
# =============================================================================

@router.post("/ragas-ground-truth", response_model=EvaluationResponse, summary="Re-evaluasi dengan ground truth (hanya precision + recall)",description=
    """
    Dipanggil ketika user mengisi ground_truth setelah auto eval selesai.

    **Efisiensi**: hanya menghitung `context_precision` dan `context_recall`.
    `faithfulness`, `answer_relevancy`, dan `risk_faithfulness` **tidak diulang** —
    diambil dari hasil auto eval yang sudah tersimpan di DB.

    Hemat ~3 LLM call Groq per re-evaluasi.

    **Syarat**: `history_id` wajib diisi agar bisa mengambil existing metrics dari DB.
    """,
)
async def evaluate_ragas_reeval(
    payload: ReevalRequest,
    db: Session = Depends(get_db),
):
    """Re-evaluasi efisien: hanya precision + recall, merge dengan skor existing."""

    if not payload.history_id:
        raise HTTPException(
            status_code=422,
            detail="history_id wajib diisi untuk re-evaluasi. "
                   "Gunakan /ragas-material untuk evaluasi pertama kali.",
        )

    # Ambil existing metrics dari DB
    existing = ProcessQueryService.get_ragas_metrics(db=db, history_id=payload.history_id)
    if not existing:
        raise HTTPException(
            status_code=404,
            detail=f"Tidak ada hasil evaluasi sebelumnya untuk history_id={payload.history_id}. "
                   "Jalankan auto eval terlebih dahulu.",
        )

    existing_metrics = existing.get("metrics", {}) or {}

    # Ambil answer_qa dari DB jika tidak dikirim ulang
    # (frontend tidak perlu kirim ulang semua data, cukup question+context+GT)
    history_data = ProcessQueryService.get_by_id(db=db, history_id=payload.history_id)

    if not history_data:
        raise HTTPException(status_code=404, detail=f"History {payload.history_id} tidak ditemukan.")

    existing_metrics = existing.get("metrics", {}) or {}

    evaluator_payload = {
        "question": payload.question or history_data.question,
        "context": payload.context or history_data.context,
        "answer": history_data.answer or "-",
        "faithfulness_text": "-",  # tidak dipakai saat is_reeval=True
        "answer_qa": history_data.answer_qa or "-",
        "answer_risk": "-",     # tidak dipakai saat is_reeval=True
        "ground_truth": payload.ground_truth,
        "source_label": "reeval_ground_truth",
        # FIX #3 — mode re-evaluasi
        "is_reeval": True,
        "existing_faithfulness":       existing_metrics.get("faithfulness"),
        "existing_answer_relevancy":   existing_metrics.get("answer_relevancy"),
        "existing_risk_faithfulness":  existing_metrics.get("risk_faithfulness"),
        "existing_segments":           existing_metrics.get("evaluated_segments", []),
        # FIX #7 (Prioritas 4)
        "existing_faithfulness_summary": existing_metrics.get("faithfulness_summary"),
        "existing_faithfulness_qa":      existing_metrics.get("faithfulness_qa"),
    }

    result = await call_evaluator(evaluator_payload, source_label="reeval_ground_truth")  # ← reuse
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=f"Re-evaluasi gagal: {result.get('error')}")

    HistoryService.update_ragas(                    # ← fix: class baru
        db=db, history_id=payload.history_id, ragas_result=result
    )

    logger.info(
        "[EvalRouter] Re-eval selesai history_id=%s | prec=%s | rec=%s",
        payload.history_id,
        result.get("metrics", {}).get("context_precision"),
        result.get("metrics", {}).get("context_recall"),
    )
    return result
