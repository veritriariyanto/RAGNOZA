"""
streamlit_app/api/prompting/integration_api.py
"""

import requests
from config.settings import settings

BASE_URL = settings.API_BASE_URL


def process_audio_integrated(
    audio_bytes: bytes,
    filename: str,
    provider: str = "whisper",
    knowledge_base: str = "uud_1945",
    style: str = "formal",
    auto_evaluate: bool = False,
    session_id: int | None = None,
) -> dict:
    """
    Kirim audio ke pipeline RAG terintegrasi.

    Returns dict dengan key:
        - status
        - transcription     {"raw": str, "repaired": str}
        - rag               {"query_used", "has_context", "context_preview",
                             "sources_count", "full_context"}
        - generated_material (dict | None)
        - fallback_message  (str | None)
        - raw_context       (str)  — full_context dari backend
        - error             (str | None)
    """
    try:
        params = {
            "provider": provider,
            "knowledge_base": knowledge_base,
            "style": style,
            "auto_evaluate": str(auto_evaluate).lower(),
        }
        if session_id is not None:
            params["session_id"] = session_id

        response = requests.post(
            f"{BASE_URL}/prompting/integration/process-integrated",
            params=params,
            files={"file": (filename, audio_bytes, "audio/wav")},
            timeout=120,
        )

        if response.status_code == 200:
            data = response.json()
            rag_data = data.get("data", {})
            full_context = rag_data.get("rag", {}).get("full_context", "")

            return {
                "status": "success",
                "transcription": rag_data.get("transcription", {}),
                "rag": rag_data.get("rag", {}),
                "generated_material": rag_data.get("generated_material"),
                "fallback_message": rag_data.get("fallback_message"),
                "history_id": rag_data.get("history_id"),
                "session_id": rag_data.get("session_id"),
                "raw_context": full_context,
                "error": None,
            }
        else:
            try:
                err_detail = response.json().get("detail", response.text)
            except Exception:
                err_detail = response.text
            return _error_response(f"Server error {response.status_code}: {err_detail}")

    except requests.exceptions.ConnectionError:
        return _error_response("Tidak dapat terhubung ke server. Pastikan backend berjalan.")
    except requests.exceptions.Timeout:
        return _error_response("Request timeout. Server terlalu lama merespons.")
    except Exception as e:
        return _error_response(str(e))

def _error_response(msg: str) -> dict:
    return {
        "status": "error",
        "transcription": {},
        "rag": {},
        "generated_material": None,
        "fallback_message": None,
        "history_id": None,
        "session_id": None,
        "raw_context": "",
        "error": msg,
    }