import requests
from config.settings import settings

BASE_URL = settings.API_BASE_URL

def get_all_history():
    response = requests.get(f"{BASE_URL}/history/")
    return response.json()

def get_history_by_id(history_id):
    response = requests.get(f"{BASE_URL}/history/{history_id}")
    return response.json()

def delete_history(history_id):
    response = requests.delete(f"{BASE_URL}/history/{history_id}")
    return response.json()