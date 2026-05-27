from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "RAG UUD Decision Support"
    
    # Database
    PGHOST: Optional[str] = None
    PGPORT: Optional[int] = None
    PGDATABASE: Optional[str] = None
    PGUSER: Optional[str] = None
    PGPASSWORD: Optional[str] = None
    PGSSLMODE: Optional[str] = None

    DATABASE_URL: Optional[str] = None

    #vektor database
    QDRANT_HOST: str
    QDRANT_PORT: int
    
    # AI Services
    GROQ_API_KEY: str
    ELEVENLABS_API_KEY: str

    class Config:
        env_file = ".env"

settings = Settings()