from groq import Groq
from app.core.config import settings

try:
    from elevenlabs.client import ElevenLabs
except ImportError:
    ElevenLabs = None

# Inisialisasi client Groq (Whisper)
groq_client = Groq(
    api_key=settings.GROQ_API_KEY
)

# Inisialisasi client ElevenLabs (opsional)
el_client = None
if ElevenLabs is not None and settings.ELEVENLABS_API_KEY:
    el_client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)