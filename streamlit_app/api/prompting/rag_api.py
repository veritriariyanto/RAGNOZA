# streamlit_app/api/rag_api.py

import requests
from config.settings import settings

BASE_URL = settings.API_BASE_URL  # e.g. "http://localhost:8000/api/v1"


# =========================================
# ASK RAG
# =========================================
def ask_rag(question: str, session_id: str | None = None) -> dict:
    """
    Kirim pertanyaan ke endpoint RAG dan kembalikan jawaban beserta sumber.

    Returns dict dengan key:
        - answer  (str)
        - sources (list[dict])  — bisa kosong []
        - error   (str | None)
    """
    if not question or not question.strip():
        return {"answer": "", "sources": [], "error": None}

    try:
        payload = {"question": question.strip()}
        if session_id:
            payload["session_id"] = session_id

        response = requests.post(
            f"{BASE_URL}/prompting/rag/ask",
            json=payload,
            timeout=60,
        )

        if response.status_code == 200:
            data = response.json()
            return {
                "answer": data.get("answer", "Tidak ada jawaban."),
                "sources": data.get("sources", []),
                "error": None,
            }
        else:
            # Coba ambil detail error dari body JSON
            try:
                err_detail = response.json().get("detail", response.text)
            except Exception:
                err_detail = response.text

            return {
                "answer": "",
                "sources": [],
                "error": f"Server error {response.status_code}: {err_detail}",
            }

    except requests.exceptions.ConnectionError:
        return {
            "answer": "",
            "sources": [],
            "error": "Tidak dapat terhubung ke server. Pastikan backend berjalan.",
        }
    except requests.exceptions.Timeout:
        return {
            "answer": "",
            "sources": [],
            "error": "Request timeout. Server terlalu lama merespons.",
        }
    except Exception as e:
        return {"answer": "", "sources": [], "error": str(e)}


# =========================================
# GET HISTORY
# =========================================
def get_chat_history(session_id: str) -> list[dict]:
    """
    Ambil riwayat chat untuk session tertentu dari backend.
    Kembalikan list of { role, content } atau [] jika gagal.
    """
    try:
        response = requests.get(
            f"{BASE_URL}/history/{session_id}",
            timeout=15,
        )
        if response.status_code == 200:
            return response.json().get("messages", [])
    except Exception:
        pass
    return []