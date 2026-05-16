# RAG API
import requests

BASE_URL = "http://127.0.0.1:8000"

def ask_rag(prompt, collection_name="uud_articles"):

    print("COLLECTION SENT:", collection_name)

    payload = {
        "prompt": prompt,
        "collection_name": collection_name
    }

    print("PAYLOAD:", payload)

    response = requests.post(
        f"{BASE_URL}/api/v1/prompting/rag/ask",
        json=payload
    )

    return response.json()