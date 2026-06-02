"""
streamlit_app/api/evaluasi/evaluation_api.py

Client untuk endpoint /evaluation/ragas.
Dipanggil dari frontend setelah material RAG diterima.
"""

import requests
from config.settings import settings

# Wajib lewat main backend agar logic update history (DB) ikut berjalan
EVALUATION_URL = settings.API_BASE_URL


def run_ragas_evaluation(
    question: str,
    context: str,
    answer: str,
    ground_truth: str | None = None,
    history_id: int | None = None,
) -> dict:
    """
    Kirim data ke endpoint evaluasi RAGAS.

    Returns dict dengan key:
        - status   (str)   "success" | "error"
        - metrics  (dict)  faithfulness, answer_relevancy, context_precision,
                           context_recall, overall_score
        - input    (dict)
        - error    (str | None)
    """
    try:
        payload = {
            "question": question,
            "context": context,
            "answer": answer,
            "source_label": "audio_rag",
        }
        if ground_truth:
            payload["ground_truth"] = ground_truth
        if history_id is not None:
            payload["history_id"] = history_id

        print(f"[RAGAS API] Mengirim ke {EVALUATION_URL}/evaluation/ragas")
        print(f"[RAGAS API] context length: {len(context)}, answer length: {len(answer)}")

        response = requests.post(
            f"{EVALUATION_URL}/evaluation/ragas",
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
            "error": "Backend evaluasi tidak dapat dijangkau. Pastikan service backend dan evaluator berjalan.",
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