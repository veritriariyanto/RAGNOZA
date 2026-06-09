# app/routes/evaluasi/evaluation_router.py
#
# FIX #3: tambah endpoint /ragas-reeval
#   - Dipanggil ketika user input ground_truth di Streamlit
#   - Ambil existing metrics dari DB via RAGHistoryService
#   - Kirim ke evaluator dengan is_reeval=True
#   - Evaluator hanya hitung precision+recall, merge dengan existing
#
# Tiga path tetap terisolasi — tidak ada yang memanggil satu sama lain.

import os
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.postgres import get_db
from app.schemas.evaluasi.evaluation_schemas import (
    MaterialEvaluationRequest,
    ReevalRequest,
    EvaluationResponse,
)
from app.schemas.prompting.generate_content import MaterialResponse
from app.services.evaluation.formatter import material_to_text, extract_segments_for_ragas
from app.services.history.rag_history_service import RAGHistoryService

logger = logging.getLogger(__name__)
ragas_router = APIRouter(tags=["Evaluation"])

EVALUATOR_BASE_URL = os.getenv("EVALUATOR_URL", "http://localhost:8001")
EVALUATOR_ENDPOINT = f"{EVALUATOR_BASE_URL}/api/v1/evaluate"
EVALUATOR_TIMEOUT = float(os.getenv("EVALUATOR_TIMEOUT_SECONDS", "900"))

# =============================================================================
# SHARED: forward ke evaluator :8001
# =============================================================================

async def _forward_to_evaluator(payload: dict) -> dict:
    """
    Fungsi Asinkron (Asynchronous) untuk meneruskan data payload evaluasi 
    ke microservice Evaluator eksternal yang berjalan di port :8001.

    Args:
        payload (dict): Data teks dan metrik yang siap dinilai oleh RAGAS.

    Returns:
        dict: Hasil skor evaluasi yang dikembalikan oleh service Evaluator.

    Raises:
        HTTPException 503: Jika service Evaluator mati/tidak bisa dihubungi.
        HTTPException 504: Jika Evaluator tidak merespons hingga batas waktu timeout.
        HTTPException 502: Jika Evaluator merespons namun mengembalikan error status (e.g., 400, 500).
    """
    try:
        async with httpx.AsyncClient(timeout=EVALUATOR_TIMEOUT) as client:
            response = await client.post(EVALUATOR_ENDPOINT, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Evaluator service tidak dapat dijangkau.")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"Evaluator timeout setelah {EVALUATOR_TIMEOUT}s.")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Evaluator error: {exc.response.text}")

def _build_payload_from_material(
    question: str, 
    context: str, 
    material: MaterialResponse,
    ground_truth, 
    source_label: str,
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
        # Karena ini jalur 'Auto-Eval' pertama kali, flag 'is_reeval' diset False.
        "is_reeval": False,
    }

# =============================================================================
# ENDPOINT 1: /ragas-auto-2metriks — Path A (auto eval dari Streamlit)
# =============================================================================

@ragas_router.post("/ragas-auto-2metriks", response_model=EvaluationResponse)
async def evaluate_ragas_auto_2metrics(
    payload: MaterialEvaluationRequest,
    db: Session = Depends(get_db),
):
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
    )

    result = await _forward_to_evaluator(evaluator_payload)

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=f"Evaluasi gagal: {result.get('error')}")

    if payload.history_id is not None:
        RAGHistoryService.update_ragas(db=db, history_id=payload.history_id, ragas_result=result)

    return result

# =============================================================================
# ENDPOINT 2: /ragas-ground-truth — Path B (user input ground truth)
# =============================================================================

@ragas_router.post("/ragas-ground-truth", response_model=EvaluationResponse, summary="Re-evaluasi dengan ground truth (hanya precision + recall)",description=
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
    existing = RAGHistoryService.get_ragas_metrics(db=db, history_id=payload.history_id)
    if not existing:
        raise HTTPException(
            status_code=404,
            detail=f"Tidak ada hasil evaluasi sebelumnya untuk history_id={payload.history_id}. "
                   "Jalankan auto eval terlebih dahulu.",
        )

    existing_metrics = existing.get("metrics", {}) or {}

    # Ambil answer_qa dari DB jika tidak dikirim ulang
    # (frontend tidak perlu kirim ulang semua data, cukup question+context+GT)
    history_data = RAGHistoryService.get_by_id(db=db, history_id=payload.history_id)
    if not history_data:
        raise HTTPException(status_code=404, detail=f"History {payload.history_id} tidak ditemukan.")

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
        "existing_overall":            existing_metrics.get("overall_score"),
        "existing_segments":           existing_metrics.get("evaluated_segments", []),
    }

    result = await _forward_to_evaluator(evaluator_payload)

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=f"Re-evaluasi gagal: {result.get('error')}")

    # Update DB dengan metrik merged (overwrite seluruh ragas_metrics)
    RAGHistoryService.update_ragas(db=db, history_id=payload.history_id, ragas_result=result)

    logger.info(
        "[Router] Re-evaluasi selesai history_id=%s | prec=%s | rec=%s | overall=%s",
        payload.history_id,
        result.get("metrics", {}).get("context_precision"),
        result.get("metrics", {}).get("context_recall"),
        result.get("metrics", {}).get("overall_score"),
    )

    return result
