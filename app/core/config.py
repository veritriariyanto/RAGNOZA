#app/core/config.py

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "RAG UUD Decision Support"
    
    # Database
    PGHOST: str
    PGPORT: int
    PGDATABASE: str
    PGUSER: str
    PGPASSWORD: str
    PGSSLMODE: str

    #vektor database
    QDRANT_HOST: str
    QDRANT_PORT: int
    
    # AI Services
    GROQ_API_KEY: str
    ELEVENLABS_API_KEY: str

    class Config:
        env_file = ".env"

settings = Settings()