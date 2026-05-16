# Audio API

import requests

BASE_URL = "http://localhost:8000"

def transcribe_audio (
        audio_file,
        provider="whisper"
):
    try:
        files = {
            "file": (
                audio_file.name,
                audio_file,
                audio_file.type
            )
        }

        response = requests.post (
            f"{BASE_URL}/api/v1/prompting/audio/process",
            files=files,
            params={
                "provider": provider
            }
        )

        if response.status_code == 200:
            return response.json()

        return {
            "error": f"Server error: {response.status_code}"
        }
    except Exception as e:
        return {
            "error": str(e)

        }