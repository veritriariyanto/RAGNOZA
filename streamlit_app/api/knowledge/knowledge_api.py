#streamlit_app/api/knowledge/knowledge_api.py

import requests
from config.settings import settings

BASE_URL = settings.API_BASE_URL

def get_knowledgebase_list() -> list[str]:
    try:
        url = f"{BASE_URL}/knowledgebase/qdran/list"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                return data
        return []  # ← kosong saja, jangan hardcode uud_1945
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
