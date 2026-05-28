import requests

from config.settings import settings

BASE_URL = settings.API_BASE_URL

def get_knowledgebase_list():

    response = requests.get(
        f"{BASE_URL}/knowledgebase/qdran/list"
    )

    return response.json()

def get_knowledgebase_stats(base_name: str):

    response = requests.get(
        f"{BASE_URL}/knowledgebase/qdran/stats/{base_name}"
    )

    return response.json()
