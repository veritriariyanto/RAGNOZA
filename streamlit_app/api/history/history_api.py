import requests
from config.settings import settings

BASE_URL = settings.API_BASE_URL

def get_all_history():
    response = requests.get(f"{BASE_URL}/history/")
    return response.json()

def get_history_by_id(history_id):
    response = requests.get(f"{BASE_URL}/history/{history_id}")
    return response.json()

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
