from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    API_BASE_URL: str = "http://localhost:8000/api/v1"

    PROJECT_NAME: str = "RAGNOZA AI"

    DEBUG: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()