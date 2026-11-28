"""Persistent webhook execution log (M4).

One row = one webhook delivery *attempt*. Incoming invocations (``/webhook/...``
and ``/api/trigger/...``) write a single row; outgoing deliveries write one row
per HTTP attempt so retries, status codes and failures are all inspectable from
the admin dashboard instead of having to dig through run logs or the database.

Payloads are redacted/size-capped before storage by ``webhook_log_service`` --
never write raw headers (secrets, signatures, API keys) to this table.
"""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.core.database import Base


class WebhookLog(Base):
    """A single observed webhook event (inbound request or outbound attempt)."""

    __tablename__ = "webhook_logs"

    id = Column(Integer, primary_key=True, index=True)

    # "incoming" | "outgoing"
    direction = Column(String(10), nullable=False, index=True)
    # e.g. "webhook", "api_trigger", "notification_webhook", "notification_slack"
    event_type = Column(String(64), nullable=False, index=True)
    # short outcome label: success | failed | rejected | duplicate | retry
    status = Column(String(24), nullable=False, default="", index=True)
    success = Column(Boolean, nullable=False, default=False, index=True)

    # Optional associations for drill-down from the run/workflow UI.
    workflow_id = Column(
        Integer, ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True, index=True
    )
    run_id = Column(
        Integer, ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tenant_id = Column(
        Integer, ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Incoming route path, or redacted outgoing URL (no query/secret token).
    endpoint = Column(String(1000), nullable=False, default="")
    method = Column(String(10), nullable=False, default="POST")
    source_ip = Column(String(64), nullable=False, default="")
    # Stable across retries; lets operators correlate a logical delivery.
    idempotency_key = Column(String(200), nullable=False, default="", index=True)

    attempt = Column(Integer, nullable=False, default=1)
    max_attempts = Column(Integer, nullable=False, default=1)
    will_retry = Column(Boolean, nullable=False, default=False)
    status_code = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    detail = Column(Text, nullable=False, default="")
    response_snippet = Column(Text, nullable=False, default="")
    # Redacted, size-capped request payload (JSON object/array or a short string).
    # JSONB on PostgreSQL; generic JSON keeps metadata portable for the few
    # legacy unit tests that still build an in-memory SQLite schema.
    request_payload = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_webhook_logs_created_direction", "created_at", "direction"),
        Index("ix_webhook_logs_workflow_created", "workflow_id", "created_at"),
        Index("ix_webhook_logs_event_created", "event_type", "created_at"),
    )
