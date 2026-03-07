from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database - SQLite
    database_url: str = "sqlite:///./data/ragdb.sqlite"
    
    # Vector Database
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None
    
    # Ollama (local LLM + embeddings)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:1b"
    ollama_embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768

    # Groq API (optional)
    groq_api_key: Optional[str] = None
    groq_model: str = "llama-3.3-70b-versatile"
    groq_embedding_model: str = "nomic-embed-text"
    
    # Application
    debug: bool = True
    log_level: str = "INFO"
    upload_dir: str = "./data/uploads"
    max_file_size: str = "50MB"
    
    # Security
    secret_key: str
    jwt_secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # Redis
    redis_url: str = "redis://localhost:6379"
    
    class Config:
        env_file = ".env"


settings = Settings()