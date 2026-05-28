import requests
from config.settings import settings

BASE_URL = settings.API_BASE_URL

def run_ragas_evaluation(
    question: str,
    context: str,
    answer: str,
    ground_truth: str | None = None,
) -> dict:
    """
    Kirim request evaluasi RAGAS ke backend FastAPI.

    Args:
        question: Pertanyaan yang dievaluasi
        context: Konteks yang digunakan RAG
        answer: Jawaban yang dihasilkan LLM 
        ground_truth: Jawaban kebenaran (jika tersedia)

    Returns:
        dict berisi status dan metrics evaluasi
    """
    try:
        response = requests.post(
            url=f"{BASE_URL}/evaluation/ragas",
            json={
                "question": question,
                "context": context,
                "answer": answer,
                "ground_truth": ground_truth or None,
            },
            timeout=120,  # evaluasi RAGAS bisa butuh waktu lama
        )
        response.raise_for_status()
        return response.json()

    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "error": "Request timeout — evaluasi RAGAS membutuhkan waktu terlalu lama.",
            "metrics": None,
        }
    except requests.exceptions.ConnectionError:
        return {
            "status": "error",
            "error": "Tidak dapat terhubung ke backend. Pastikan server FastAPI berjalan.",
            "metrics": None,
        }
    except requests.exceptions.HTTPError as e:
        try:
            detail = e.response.json().get("detail", str(e))
        except Exception:
            detail = str(e)
        return {
            "status": "error",
            "error": detail,
            "metrics": None,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "metrics": None,
        }