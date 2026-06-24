#streamlit_app/api/knowledge/knowledge_api.py

import requests
from config.settings import settings

BASE_URL = settings.API_BASE_URL


def get_knowledgebase_list() -> list[str]:
    try:
        url = f"{BASE_URL}/knowledgebase/qdran/list"
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                return data
        return []
    except Exception as e:
        print(f"[KB DEBUG] Exception: {e}")
        return []


def get_knowledgebase_stats(base_name: str) -> dict:
    try:
        response = requests.get(
            f"{BASE_URL}/knowledgebase/qdran/stats/{base_name}",
            timeout=10,
        )
        if response.status_code == 200:
            return response.json()
        else:
            return {
                "status": "error",
                "error": f"HTTP {response.status_code}: collection '{base_name}' tidak ditemukan",
                "parent_count": 0,
                "child_count": 0,
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "parent_count": 0,
            "child_count": 0,
        }


def upload_and_clean(pdf_bytes: bytes, filename: str) -> dict:
    """POST /api/v1/knowledgebase/chunking/upload — cleaning only."""
    try:
        response = requests.post(
            f"{BASE_URL}/knowledgebase/chunking/upload",
            files={"file": (filename, pdf_bytes, "application/pdf")},
            timeout=120,
        )
        if response.status_code == 200:
            return {"success": True, "data": response.json()}
        else:
            detail = response.json().get("detail", response.text)
            return {"success": False, "error": detail}
    except Exception as e:
        return {"success": False, "error": str(e)}


def process_and_chunk(
    pdf_bytes: bytes,
    filename: str,
    include_raw_chunks: bool = True,
    embed: bool = False,
    collection: str | None = None,
) -> dict:
    """POST /api/v1/knowledgebase/chunking/process — cleaning + chunking (+embed)."""
    try:
        params = {
            "include_chunks_preview": "true",
            "include_raw_chunks": str(include_raw_chunks).lower(),
            "embed": str(embed).lower(),
        }
        if collection:
            params["collection"] = collection

        response = requests.post(
            f"{BASE_URL}/knowledgebase/chunking/process",
            files={"file": (filename, pdf_bytes, "application/pdf")},
            params=params,
            timeout=300,
        )
        if response.status_code == 200:
            return {"success": True, "data": response.json()}
        else:
            detail = response.json().get("detail", response.text)
            return {"success": False, "error": detail}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_knowledgebase(base_name: str) -> dict:
    """DELETE /api/v1/knowledgebase/qdran/delete/{base_name}"""
    try:
        response = requests.delete(
            f"{BASE_URL}/knowledgebase/qdran/delete/{base_name}",
            timeout=30,
        )
        if response.status_code == 200:
            return {"success": True, "data": response.json()}
        else:
            detail = response.json().get("detail", response.text)
            return {"success": False, "error": detail}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_knowledgebase_preview(base_name: str, limit: int = 10) -> dict:
    """GET /api/v1/knowledgebase/qdran/preview/{base_name}"""
    try:
        response = requests.get(
            f"{BASE_URL}/knowledgebase/qdran/preview/{base_name}",
            params={"limit": limit},
            timeout=15,
        )
        if response.status_code == 200:
            return {"success": True, "data": response.json()}
        else:
            detail = response.json().get("detail", response.text)
            return {"success": False, "error": detail}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_kb_monitor_data(base_name: str, preview_limit: int = 5) -> dict:
    """GET /api/v1/knowledgebase/qdran/monitor/{base_name} — satu call untuk semua data monitoring."""
    try:
        response = requests.get(
            f"{BASE_URL}/knowledgebase/qdran/monitor/{base_name}",
            params={"preview_limit": preview_limit},
            timeout=20,
        )
        if response.status_code == 200:
            return {"success": True, "data": response.json()}
        else:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            return {"success": False, "error": detail}
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_similarity(
    base_name: str,
    query: str,
    section_type: str = None,
    pasal_type: str = None,
    limit: int = 5,
    score_threshold: float = 0.15,
) -> dict:
    """POST /api/v1/knowledgebase/qdran/search/{base_name}"""
    try:
        payload = {
            "query": query,
            "limit": limit,
            "score_threshold": score_threshold,
        }
        if section_type and section_type.strip().lower() not in ("semua", "all", ""):
            payload["section_type"] = section_type
        if pasal_type and str(pasal_type).strip():
            payload["pasal_type"] = pasal_type

        response = requests.post(
            f"{BASE_URL}/knowledgebase/qdran/search/{base_name}",
            data=payload,
            timeout=25,
        )
        if response.status_code == 200:
            return {"success": True, "data": response.json()}
        else:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            return {"success": False, "error": detail}
    except Exception as e:
        return {"success": False, "error": str(e)}
