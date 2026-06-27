"""
app/services/evaluation/evaluation_hook.py

Modul ini menjalankan evaluasi RAGAS secara otomatis di background setelah
RAG pipeline selesai menjawab pertanyaan user.

PERUBAHAN ARSITEKTUR V1:
    Sebelumnya → import langsung EvaluationService (menyebabkan konflik ragas vs langchain)
    Sekarang   → HTTP POST ke evaluator service (port 8001) via httpx

PERUBAHAN ARSITEKTUR V2:
    Telah di-update untuk mendukung ekstraksi segmen material (Summary, QA, Risk)
    sebelum menembak HTTP POST ke evaluator service (port 8001).


Alur:
    User Question
         ↓
    RAG Pipeline (STT → Repair → Search → LLM)
         ↓
    answer + context tersedia
         ↓
    ┌─── return response ke user  (tidak blocking)
    └─── trigger_auto_evaluation()
              ↓
         HTTP POST → evaluator:8001/api/v1/evaluate  (background task)
              ↓
         Hasil RAGAS di-log (dan bisa disimpan ke DB jika diperlukan)
"""

# app/services/evaluation/evaluation_hook.py

import logging
from typing import Optional

from app.services.evaluation.evaluation_client import call_evaluator
from app.services.evaluation.evaluation_db_service import update_ragas_in_db
from app.services.evaluation.formatter import material_to_text, extract_segments_for_ragas
from app.schemas.prompting.generate_content import MaterialResponse

logger = logging.getLogger(__name__)

# =============================================================================
# CORE FUNCTION (Fungsi Utama / Hook)
# =============================================================================

async def trigger_auto_evaluation(
    question: str,
    context: str,
    material: MaterialResponse,
    ground_truth: Optional[str] = None,
    source_label: str = "rag_pipeline",
    history_id: Optional[int] = None,
    context_chunks: Optional[list[str]] = None,   # ← tambah ini
    # CATATAN: jangan terima 'db' dari request — buat session baru di dalam
) -> dict:
    """
    Fungsi Entry-Point utama (Hook) untuk memicu evaluasi otomatis RAGAS secara asinkron.
    Fungsi ini dieksekusi sebagai FastAPI BackgroundTask agar user di frontend tidak perlu 
    menunggu proses hitung LLM yang lama saat selesai men-generate materi hukum.
    """
    # 1. SEGMENTASI TEKS HUKUM:
    # Memecah objek MaterialResponse yang kompleks menjadi komponen teks spesifik 
    # (Summary untuk faithfulness, LegalQA untuk relevancy, RiskReview untuk risk_faithfulness)
    segments = extract_segments_for_ragas(material)
    
    # 2. Ambil teks lengkap untuk cadangan log ( backward compatibility )
    full_answer = material_to_text(material)

    logger.info(
        "[AutoEval:%s] Mengirim data tersegmentasi ke evaluator | q=%d chars | ctx=%d chars | ans_full=%d chars",
        source_label, len(question), len(context), len(full_answer),
    )

    # 3. STRUKTURISASI PAYLOAD JSON:
    # Menyusun kamus data (dictionary) yang sesuai dengan kontrak skema API Evaluator :8001
    payload = {
        "question": question,
        "context": context,
        "answer": full_answer,

        "faithfulness_text": segments["faithfulness"],
        "answer_qa": segments["qa"],
        "answer_risk": segments["risk"],

        "ground_truth": ground_truth,
        "source_label": source_label,
        "context_chunks": context_chunks or [],   # ← tambah ini
    }

    # Tambahkan di dalam _build_payload_from_material sebelum return dict
    if not question or len(question.strip()) == 0:
        logger.error("[PayloadCheck] 🚨 CRITICAL: Question kosong dari hulu pipeline!")
    
    logger.info(
        "[PayloadCheck] question='%s' | faithfulness_text_len=%d | answer_qa='%s'",
        question[:100] if question else "EMPTY",
        len(segments.get("faithfulness", "")),
        segments.get("qa", "")[:200],
    )

    # 4. EKSEKUSI PANGGILAN HTTP:
    # Menembak microservice evaluator secara asinkron dan menunggu hasilnya kembali
    result = await call_evaluator(payload, source_label)

    # 5. PENCATATAN LOG HASIL EVALUASI:
    if result.get("status") == "success":
        metrics = result.get("metrics") or {}
        logger.info(
            "[AutoEval:%s] ✅ Selesai | faith=%.4f | relevancy=%.4f | "
            "precision=%s | recall=%s | overall=%s",
            source_label,
            metrics.get("faithfulness") or 0.0,
            metrics.get("answer_relevancy") or 0.0,
            f"{metrics['context_precision']:.4f}" if metrics.get("context_precision") else "N/A",
            f"{metrics['context_recall']:.4f}"    if metrics.get("context_recall")    else "N/A",
        )
    else:
        logger.warning(
            "[AutoEval:%s] ⚠️ Error dari evaluator: %s",
            source_label, result.get("error"),
        )

    # 6. SINKRONISASI DATABASE (PERSISTENCE):
    # Jika history_id dikirimkan, jalankan helper untuk menyimpan skor akhir ke dalam database PostgreSQL
    if history_id is not None:
        update_ragas_in_db(history_id, result)
    else:
        logger.debug("[AutoEval:%s] history_id tidak ada — DB tidak diupdate.", source_label)

    return result