import requests

BASE_URL = "http://localhost:8000/api/v1"

def get_all_history():
    response = requests.get(f"{BASE_URL}/history/")
    return response.json()

def get_history_by_id(history_id):
    response = requests.get(f"{BASE_URL}/history/{history_id}")
    return response.json()

def delete_history(history_id):
    response = requests.delete(f"{BASE_URL}/history/{history_id}")
    return response.json()