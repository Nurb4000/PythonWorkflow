"""
Application settings and configuration
"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Application
    app_name: str = "Python Workflow System"
    debug: bool = True
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./workflow.db"
    
    # CORS
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    # AI / llama.cpp
    llama_cpp_url: str = "http://localhost:8081"
    llama_cpp_model: str = "default"
    
    # Security
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # Scheduler
    scheduler_timezone: str = "UTC"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
