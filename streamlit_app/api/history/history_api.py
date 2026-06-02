# streamlit_app/api/history/history_api.py

import logging
import requests
from config.settings import settings

BASE_URL = settings.API_BASE_URL
logger = logging.getLogger(__name__)


def get_all_history() -> dict:
    try:
        # Coba tanpa trailing slash dulu
        resp = requests.get(
            f"{BASE_URL}/history",
            timeout=10,
            allow_redirects=True,
        )
        
        # Log detail jika gagal — untuk debug
        if resp.status_code != 200:
            logger.error(
                "[HistoryAPI] get_all_history gagal: status=%d | url=%s | body=%s",
                resp.status_code, resp.url, resp.text[:300]
            )
            return {}
            
        return resp.json()
    except Exception as e:
        logger.error("[HistoryAPI] get_all_history exception: %s", e)
        return {}


def get_history_detail(history_id: int) -> dict:
    try:
        resp = requests.get(
            f"{BASE_URL}/history/{history_id}",
            timeout=10,
            allow_redirects=True,
        )
        return resp.json() if resp.status_code == 200 else {}
    except Exception:
        return {}


def delete_history(history_id: int) -> bool:
    try:
        resp = requests.delete(
            f"{BASE_URL}/history/{history_id}",
            timeout=10,
            allow_redirects=True,
        )
        return resp.status_code == 200
    except Exception:
        return False
    
# Tambahan untuk update title session
def update_history_title(
    history_id: int,
    session_title: str,
) -> bool:
    try:
        resp = requests.put(
            f"{BASE_URL}/history/{history_id}/title",
            json={
                "session_title": session_title
            },
            timeout=10,
            allow_redirects=True,
        )

        print("STATUS =", resp.status_code)
        print("BODY =", resp.text)

        return resp.status_code == 200

    except Exception as e:
        logger.error(
            "[HistoryAPI] update_history_title error: %s",
            e
        )
        return False