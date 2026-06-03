# api/history/history_api.py

import requests
from config.settings import settings

BASE_URL = settings.API_BASE_URL      # Contoh: http://localhost:8000/api/v1
HISTORY_PREFIX = "/history"           # Sesuaikan dengan nama route di backend kamu

def get_all_history():
    try:
        # 🛠️ HAPUS tanda miring "/" di akhir agar URL menjadi .../v1/history
        response = requests.get(f"{BASE_URL}") 
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"Gagal mengambil data: {str(e)}"}

def get_history_by_id(history_id: int):
    try:
        # URL menjadi .../v1/history/12
        response = requests.get(f"{BASE_URL}/{history_id}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"Gagal mengambil detail: {str(e)}"}

def delete_history(history_id: int):
    try:
        # URL menjadi .../v1/history/12
        response = requests.delete(f"{BASE_URL}{HISTORY_PREFIX}/{history_id}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"status": "error", "message": f"Gagal menghapus history: {str(e)}"}