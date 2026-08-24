"""
Application settings and configuration
"""
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import List
from pydantic import field_validator


class Settings(BaseSettings):
    # Application
    app_name: str = "Instant Workflow"
    debug: bool = True
    
    # Database (PostgreSQL only)
    database_url: str = "postgresql+asyncpg://workflow_user:workflow_password@postgres:5432/workflow_db"
    
    @field_validator('database_url')
    @classmethod
    def check_database_url(cls, v):
        if not v.startswith('postgresql+asyncpg://'):
            raise ValueError('database_url must start with postgresql+asyncpg:// (SQLite not supported)')
        return v
    
    # CORS
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    # AI / llama.cpp
    llama_cpp_url: str = "http://localhost:8081"
    llama_cpp_model: str = "default"
    
    # Security
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080
    
    # Scheduler
    scheduler_timezone: str = "UTC"
    
    # SMTP / admin notices (leave host empty to disable)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@pythonworkflow.local"
    smtp_tls: bool = True
    admin_notify_email: str = ""
    
    # Webhook authentication (leave empty to disable secret verification)
    webhook_secret: str = ""
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()


def resolve_project_root() -> Path:
    """Return the directory that contains the ``knowledge-base`` folder.

    Walks up from the app package so it works both in the dev checkout
    (``<repo>/backend/app/...``) and inside the container where the code is
    mounted at ``/app/...`` and the knowledge base sits at ``/app/knowledge-base``.
    """
    current = Path(__file__).resolve().parent  # app/core
    while current != current.parent:
        if (current / "knowledge-base").is_dir():
            return current
        current = current.parent
    return Path(__file__).resolve().parent.parent.parent.parent
