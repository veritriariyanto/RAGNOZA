#config/settings.py

from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    API_BASE_URL: str = "http://localhost:8000/api/v1"
    EVALUATOR_BASE_URL: str = "http://localhost:8001/api/v1"  # ← tambah ini

    PROJECT_NAME: str = "RAGNOZA AI"

    DEBUG: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()