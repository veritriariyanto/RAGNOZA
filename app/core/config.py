from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "RAG UUD Decision Support"
    
    # Database
    PGHOST: str
    PGPORT: int
    PGDATABASE: str
    PGUSER: str
    PGPASSWORD: str
    
    # AI Services
    GROQ_API_KEY: str
    QDRANT_HOST: str
    
    class Config:
        env_file = ".env"

settings = Settings()