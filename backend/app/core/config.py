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
    
    # AI / OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-3.5-turbo"
    openai_base_url: str = "https://api.openai.com/v1"
    
    # AI provider selection (llama_cpp or openai)
    ai_provider: str = "llama_cpp"
    
    # LDAP configuration (optional)
    ldap_server_url: str = ""  # e.g., ldap://ldap.example.com:389
    ldap_base_dn: str = ""  # e.g., dc=example,dc=com
    ldap_bind_dn: str = ""  # Service account DN for binding
    ldap_bind_password: str = ""  # Service account password
    ldap_user_filter: str = "(objectClass=person)"  # LDAP filter for users
    ldap_username_attribute: str = "uid"  # Attribute to use as username
    ldap_email_attribute: str = "mail"  # Attribute for email
    ldap_fullname_attribute: str = "cn"  # Attribute for full name
    ldap_sync_enabled: bool = False  # Enable automatic sync
    ldap_sync_interval_hours: int = 24  # How often to sync
    
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
