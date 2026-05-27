from groq import Groq
from elevenlabs.client import ElevenLabs
from app.core.config import settings

# Inisialisasi client Groq (Whisper)
groq_client = Groq(
    api_key=settings.GROQ_API_KEY
)

# Inisialisasi client ElevenLabs
el_client = ElevenLabs(
    api_key=settings.ELEVENLABS_API_KEY
)