"""
streamlit_app/api/evaluasi/evaluation_api.py

PERBAIKAN #1 (Data Integrity):
    Sebelumnya → mengirim placeholder "-" untuk semua segmen
    Sekarang   → mengirim MaterialResponse ke endpoint baru /evaluation/ragas-auto-2metriks
                 yang melakukan ekstraksi segmen di sisi backend (port 8000).

Kenapa tidak ekstraksi di sini:
    Frontend (Streamlit) tidak boleh tahu detail internal MaterialResponse.
    Jika schema MaterialResponse berubah, hanya backend yang perlu diupdate.
"""

import requests
from config.settings import settings

EVALUATION_URL = settings.API_BASE_URL


def run_ragas_evaluation(
    question: str,
    context: str,
    material_dict: dict,
    ground_truth: str | None = None,
    history_id: int | None = None,
) -> dict:
    """
    Kirim MaterialResponse (sebagai dict) ke endpoint evaluasi RAGAS.

    PERUBAHAN:
        - Parameter 'answer' (plain text) diganti 'material_dict' (dict MaterialResponse).
        - Endpoint berubah dari /evaluation/ragas ke /evaluation/ragas-auto-2metriks
        - Backend yang melakukan extract_segments_for_ragas() — bukan frontend.

    Args:
        question:      Pertanyaan user.
        context:       Konteks dokumen dari RAG pipeline.
        material_dict: MaterialResponse.model_dump() — dict hasil generate material.
        ground_truth:  Jawaban ideal dari legal expert (opsional).
        history_id:    ID history untuk update DB (opsional).

    Returns:
        dict dengan key: status, metrics, input, error
    """
    try:
        payload = {
            "question": question,
            "context": context,
            "material": material_dict,
        }
        if ground_truth:
            payload["ground_truth"] = ground_truth
        if history_id is not None:
            payload["history_id"] = history_id

        print(f"[RAGAS API] Mengirim ke {EVALUATION_URL}/evaluation/ragas-auto-2metriks")
        print(f"[RAGAS API] context length: {len(context)}")

        response = requests.post(
            f"{EVALUATION_URL}/evaluation/ragas-auto-2metriks",
            json=payload,
            timeout=900,
        )

        print(f"[RAGAS API] Response status: {response.status_code}")

        if response.status_code == 200:
            return response.json()
        else:
            try:
                err_detail = response.json().get("detail", response.text)
            except Exception:
                err_detail = response.text
            return {
                "status": "error",
                "metrics": None,
                "input": {},
                "error": f"Server error {response.status_code}: {err_detail}",
            }

    except requests.exceptions.ConnectionError:
        return {
            "status": "error",
            "metrics": None,
            "input": {},
            "error": "Backend evaluasi tidak dapat dijangkau.",
        }
    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "metrics": None,
            "input": {},
            "error": "Evaluasi timeout — RAGAS membutuhkan waktu lebih lama dari biasanya.",
        }
    except Exception as e:
        return {"status": "error", "metrics": None, "input": {}, "error": str(e)}

def run_ragas_reeval(
    ground_truth: str,
    history_id: int,
    question: str | None = None,
    context: str | None = None,
) -> dict:
    """
    Re-evaluasi efisien — hanya hitung precision + recall.
    Memanggil endpoint /evaluation/ragas-ground-truth (FIX #3).
    """
    try:
        payload = {
            "history_id": history_id,
            "ground_truth": ground_truth,
        }
        if question:
            payload["question"] = question
        if context:
            payload["context"] = context

        response = requests.post(
            f"{EVALUATION_URL}/evaluation/ragas-ground-truth",
            json=payload,
            timeout=900,
        )

        if response.status_code == 200:
            return response.json()
        else:
            try:
                err_detail = response.json().get("detail", response.text)
            except Exception:
                err_detail = response.text
            return {
                "status": "error",
                "metrics": None,
                "input": {},
                "error": f"Server error {response.status_code}: {err_detail}",
            }

    except requests.exceptions.ConnectionError:
        return {"status": "error", "metrics": None, "input": {},
                "error": "Backend evaluasi tidak dapat dijangkau."}
    except requests.exceptions.Timeout:
        return {"status": "error", "metrics": None, "input": {},
                "error": "Re-evaluasi timeout."}
    except Exception as e:
        return {"status": "error", "metrics": None, "input": {}, "error": str(e)}