"""
streamlit_app/api/prompting/integration_api.py
 
Client untuk endpoint /prompting/integration/process-integrated.
Mengirim audio dan menerima hasil material + metadata RAG.
"""

import requests
from config.settings import settings

BASE_URL = settings.API_BASE_URL  # e.g. "http://localhost:8000/api/v1"

def process_audio_integrated(
        audio_bytes: bytes,
        filename: str,
        provider: str = "whisper",
        knowledge_base: str = "uud_1945",
        style: str = "formal",
) -> dict:
    """
    Kirim audio ke pipeline RAG terintegrasi.
 
    Returns dict dengan key:
        - status            (str)  "success" | "error"
        - transcription     (dict) {"raw": str, "repaired": str}
        - rag               (dict) {"query_used", "has_context", "context_preview", "sources_count"}
        - generated_material(dict | None)  hasil SPK hukum
        - fallback_message  (str | None)
        - raw_context       (str)  konteks lengkap untuk evaluasi RAGAS
        - error             (str | None)
    """
    try:
        response = requests.post(
            f"{BASE_URL}/prompting/integration/process-integrated",
            params={
                "provider": provider,
                "knowledge_base": knowledge_base,
                "style": style,
            },
            files={"file": (filename, audio_bytes, "audio/wav")},
            timeout=120,
        )

        if response.status_code == 200:
            data = response.json()
            rag_data = data.get("data", {})
            status = data.get("status", "success")
            if status == "success" and rag_data.get("generated_material") is None and rag_data.get("fallback_message"):
                status = "failed"

            return {
                "status": status,
                "session_id": data.get("session_id"),
                "transcription": rag_data.get("transcription", {}),
                "rag": rag_data.get("rag", {}),
                "generated_material": rag_data.get("generated_material"),
                "fallback_message": rag_data.get("fallback_message"),
                # context_preview sudah dipotong 500 char di backend,
                # tapi untuk RAGAS kita butuh yang lengkap — ambil dari preview dulu,
                # karena backend hanya return preview di response ini
                "raw_context": rag_data.get("rag", {}).get("full_context", ""),
                "error": None,
            }
        else:
            try:
                err_detail = response.json().get("detail", response.text)
            except Exception:
                err_detail = response.text
            return {
                "status": "error",
                "transcription": {},
                "rag": {},
                "generated_material": None,
                "fallback_message": None,
                "raw_context": "",
                "error": f"Server error {response.status_code}: {err_detail}",
            }
        
    except requests.exceptions.ConnectionError:
        return {
            "status": "error",
            "transcription": {},
            "rag": {},
            "generated_material": None,
            "fallback_message": None,
            "raw_context": "",
            "error": "Tidak dapat terhubung ke server. Pastikan backend berjalan.",
        }
    
    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "transcription": {},
            "rag": {},
            "generated_material": None,
            "fallback_message": None,
            "raw_context": "",
            "error": "Request timeout. Server terlalu lama merespons.",
        }
    
    except Exception as e:
        return {
            "status": "error",
            "transcription": {},
            "rag": {},
            "generated_material": None,
            "fallback_message": None,
            "raw_context": "",
            "error": str(e),
        }