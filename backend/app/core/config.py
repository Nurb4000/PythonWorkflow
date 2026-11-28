"""
Application settings and configuration
"""
import logging
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import List
from pydantic import field_validator, model_validator

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # Application
    app_name: str = "Instant Workflow"
    # L3 fix: default to False; set DEBUG=True explicitly for development.
    # When False, the JWT secret key validator raises on the default value.
    debug: bool = False
    
    # Database (PostgreSQL only).
    # L3 fix: no shipped credentials. In deployment DATABASE_URL is provided via
    # environment variable / secret manager (docker-compose sets it); this
    # placeholder only serves as a non-sensitive local fallback.
    database_url: str = "postgresql+asyncpg://localhost:5432/workflow_db"
    
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
    openai_model: str = "gpt-4o"
    openai_base_url: str = "https://api.openai.com/v1"
    
    # AI / Anthropic Claude (F3)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    anthropic_base_url: str = "https://api.anthropic.com/v1"

    # AI provider selection (llama_cpp, openai, or anthropic)
    ai_provider: str = "llama_cpp"

    # M8 fix: optional ordered fallback providers, e.g. "openai,llama_cpp".
    # Empty (the default) preserves single-provider behavior exactly. Parsing is
    # done in ai_service.ai_provider_chain() so both comma-separated env values
    # and runtime API updates are accepted.
    ai_fallback_providers: str = ""
    
    # M7 fix: per-user AI usage throttle. Caps the number of paid LLM requests
    # a single user may make within a rolling window to prevent unbounded cost
    # from chaining generate/assist calls. Tune via env vars.
    ai_requests_per_window: int = 100
    ai_request_window_seconds: int = 3600

    # M5 fix: per-IP API rate limiting for the high-cost / high-touch endpoints
    # (/ai/*, /data-query/*, /data-export/*). Caps how many requests a single
    # source IP may make within a rolling window before the shared
    # `require_api_rate_limit` dependency returns HTTP 429. This bounds request
    # frequency per IP for DoS/abuse; it is separate from the login brute-force
    # guard (per-username lockout, app.api.auth) and from the per-user AI cost
    # throttle above (which caps LLM spend per account). Tune via env vars.
    api_requests_per_window: int = 60
    api_request_window_seconds: int = 60

    # G7 fix: export alerting. Cap hits (requested/clamped or row count at the
    # 100k hard cap) and export rate-limit hits are pushed through the configured
    # admin notification channels. Repeated identical events are deduped for this
    # many seconds so one client/table cannot spam operators.
    export_alerts_enabled: bool = True
    export_alert_cooldown_seconds: int = 300

    # G3 fix: per-step retry backoff policy. Per-step retries previously used a single
    # fixed delay, so transient failures re-hit the same limit and waste budget. These
    # tune an exponential-backoff curve (base * multiplier^(attempt-1), capped at
    # max_delay, with full jitter). A step's `retry_delay_seconds` overrides the base
    # for that step specifically. Tune via env vars.
    retry_backoff_base_seconds: float = 1.0
    retry_backoff_multiplier: float = 2.0
    retry_backoff_max_seconds: float = 60.0

    # M4 fix: webhook execution logs (every inbound invocation and outbound
    # delivery attempt) are kept in the DB for operator inspection. Bound both
    # retention and per-row payload size so the audit table cannot grow forever.
    webhook_log_retention_days: int = 30
    webhook_log_payload_chars: int = 4000
    
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
    access_token_expire_minutes: int = 1440
    # Refresh-token rotation (feature gap #1b). Opaque, DB-backed, bcrypt-hashed
    # tokens that outlive the access token. Each successful rotation issues a new
    # refresh token and retires the presented one; replaying a retired token is
    # treated as a leak and revokes the whole chain for the user.
    refresh_token_expire_days: int = 7
    refresh_token_rotation: bool = True

    @model_validator(mode="after")
    def check_secret_key(self):
        if self.secret_key == "change-me-in-production":
            # H2 fix: raise in production (debug=False), warn in dev
            if not self.debug:
                raise ValueError(
                    "SECRET_KEY is still the default value. "
                    "Set SECRET_KEY env var for production deployments."
                )
            logger.warning(
                "SECRET_KEY is still the default value. "
                "Set SECRET_KEY env var for production deployments."
            )
        return self
    
    # Database echo (separate from debug to avoid SQL spam in prod)
    sql_echo: bool = False

    # Logging — "text" for human-readable, "json" for structured logs
    log_format: str = "text"

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
    
    # Webhook authentication. Verification now fails closed: if this is empty,
    # POST /webhook/{workflow_id} rejects triggers with 401 (findings #30).
    # Reused as the shared secret for signing *outgoing* G4 notification webhooks.
    webhook_secret: str = ""

    # G4 external notification channels (leave empty to disable that channel).
    # Runtime overrides can be persisted in system_settings and re-applied at
    # startup via load_channel_overrides().
    slack_webhook_url: str = ""
    webhook_url: str = ""  # generic outgoing G4 webhook endpoint

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Ignore unknown env vars (e.g. TEST_DATABASE_URL, used by the test suite
        # to point DATABASE_URL at the isolated DB). pydantic-settings defaults to
        # extra="forbid", which would make Settings() crash on any non-mapping env
        # var; tests and deployments routinely export such variables.
        extra = "ignore"


settings = Settings()


def resolve_project_root() -> Path:
    """Return the directory that contains the ``knowledge-base`` folder.

    Walks up from the app package so it works both in the dev checkout
    (``<repo>/backend/app/...``) and inside the container where the code is
    mounted at ``/app/...`` and the knowledge base sits at ``/app/knowledge-base``.

    Robustness (findings #36): prefer a ``knowledge-base`` that actually has
    content. Without this, a stray *empty* ``backend/knowledge-base/`` directory
    in a dev checkout shadows the real repo-root ``knowledge-base/`` and the
    resolver returns the wrong root — so ``template_service`` and ``ai_service``
    silently load zero templates / KB prompts (no error). Falls back to the
    closest ``knowledge-base`` dir, then the historical default, if none are
    populated.
    """
    current = Path(__file__).resolve().parent  # app/core
    fallback = None
    while current != current.parent:
        kb = current / "knowledge-base"
        if kb.is_dir():
            if any(kb.iterdir()):  # populated knowledge-base wins
                return current
            if fallback is None:  # remember the closest empty one as a fallback
                fallback = current
        current = current.parent
    return fallback or Path(__file__).resolve().parent.parent.parent.parent
