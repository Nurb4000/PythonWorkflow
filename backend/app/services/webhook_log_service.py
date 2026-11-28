"""Persistent webhook execution log helpers (M4).

Every webhook event -- an inbound invocation or one attempt at an outbound
delivery -- is recorded in ``webhook_logs``. Logging is strictly best-effort:
it must never turn a successful delivery/run into a failure, and a DB problem
must never stop the outgoing sender from retrying.

Security notes
--------------
* Only redacted, size-capped payloads are stored. Never pass request *headers*
  here: they carry webhook secrets, HMAC signatures and API keys.
* Outgoing URLs are sanitised (query/userinfo removed, long opaque path tokens
  masked) before storage, since Slack/webhook URLs themselves are credentials.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import delete

from app.core.config import settings
from app.core.database import async_session_factory
from app.models.webhook_log import WebhookLog

logger = logging.getLogger(__name__)

DIRECTION_INCOMING = "incoming"
DIRECTION_OUTGOING = "outgoing"

EVENT_WEBHOOK = "webhook"
EVENT_API_TRIGGER = "api_trigger"
EVENT_NOTIFICATION_WEBHOOK = "notification_webhook"
EVENT_NOTIFICATION_SLACK = "notification_slack"

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_REJECTED = "rejected"
STATUS_DUPLICATE = "duplicate"
STATUS_RETRY = "retry"

# Substrings that mark a payload field as sensitive. Matching is deliberately
# generous: a false positive (an innocent "token" field being masked) is cheap,
# a false negative (a secret stored in plaintext) is not.
_SECRET_FIELD_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "signature",
    "credential",
    "private_key",
)
_REDACTED = "<redacted>"
_MAX_LIST_ITEMS = 100

# Prune at most once an hour so every delivery does not pay for a DELETE.
_PRUNE_INTERVAL_SECONDS = 3600
_last_prune: float = 0.0


def _is_secret_field(key: Any) -> bool:
    normalised = str(key).lower().replace("-", "_")
    return any(part in normalised for part in _SECRET_FIELD_PARTS)


def _payload_limit() -> int:
    return max(256, int(getattr(settings, "webhook_log_payload_chars", 4000)))


def redact_payload(payload: Any, max_chars: Optional[int] = None) -> Any:
    """Return a JSON-safe copy of *payload* with secrets masked and size capped.

    Returns ``None`` for a missing payload. Oversized values are replaced by a
    small ``{"_truncated": true, "preview": "..."}`` marker rather than silently
    storing a huge object in an audit table.
    """
    if payload is None:
        return None
    cap = max_chars if max_chars is not None else _payload_limit()

    if isinstance(payload, dict):
        clean: dict = {}
        for key, value in list(payload.items())[:_MAX_LIST_ITEMS]:
            clean[str(key)] = _REDACTED if _is_secret_field(key) else redact_payload(value, cap)
        if len(payload) > _MAX_LIST_ITEMS:
            clean["_truncated_fields"] = len(payload) - _MAX_LIST_ITEMS
        data: Any = clean
    elif isinstance(payload, (list, tuple, set)):
        items = list(payload)
        data = [redact_payload(v, cap) for v in items[:_MAX_LIST_ITEMS]]
        if len(items) > _MAX_LIST_ITEMS:
            data.append(f"... {len(items) - _MAX_LIST_ITEMS} more items")
    elif isinstance(payload, bytes):
        data = payload.decode("utf-8", errors="replace")
    elif isinstance(payload, (str, int, float, bool)):
        data = payload
    else:
        data = str(payload)

    try:
        encoded = json.dumps(data, default=str)
    except (TypeError, ValueError):
        return "<unserializable payload>"
    if len(encoded) > cap:
        return {"_truncated": True, "preview": encoded[:cap]}
    return data


def safe_endpoint(value: str, *, incoming: bool = False) -> str:
    """Return an endpoint safe to persist (no query strings or secret tokens).

    Inbound routes are stored verbatim (they contain no credentials). Outbound
    URLs are stripped of userinfo/query/fragment and any opaque path segment of
    20+ characters is masked -- Slack incoming-webhook tokens live in the path.
    """
    if not value:
        return ""
    if incoming:
        return value[:1000]
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        if ":" in host:  # IPv6 literal
            host = f"[{host}]"
        if parts.port:
            host = f"{host}:{parts.port}"
        segments = [
            "***"
            if len(seg) >= 20 and re.fullmatch(r"[A-Za-z0-9_-]+", seg)
            else seg
            for seg in parts.path.split("/")
        ]
        return urlunsplit((parts.scheme, host, "/".join(segments), "", ""))[:1000]
    except (TypeError, ValueError):
        return "<invalid-url>"


def snippet(value: Any, limit: int = 500) -> str:
    """Short, single-line detail/response snippet for the dashboard."""
    if value is None:
        return ""
    return str(value).replace("\n", " ").strip()[:limit]


async def log_webhook_event(
    *,
    direction: str,
    event_type: str,
    endpoint: str,
    success: bool,
    status: str = "",
    workflow_id: Optional[int] = None,
    run_id: Optional[int] = None,
    tenant_id: Optional[int] = None,
    source_ip: str = "",
    idempotency_key: str = "",
    method: str = "POST",
    attempt: int = 1,
    max_attempts: int = 1,
    will_retry: bool = False,
    status_code: Optional[int] = None,
    duration_ms: Optional[int] = None,
    detail: str = "",
    response_snippet: str = "",
    request_payload: Any = None,
) -> Optional[int]:
    """Persist one webhook event. Never raises; returns the row id on success.

    Uses its own DB session so outbound logging is independent of the caller's
    transaction (notification dispatch often happens after a run commits).
    """
    global _last_prune
    try:
        async with async_session_factory() as db:
            row = WebhookLog(
                direction=direction,
                event_type=event_type,
                status=status or (STATUS_SUCCESS if success else STATUS_FAILED),
                success=bool(success),
                workflow_id=workflow_id,
                run_id=run_id,
                tenant_id=tenant_id,
                endpoint=safe_endpoint(endpoint, incoming=direction == DIRECTION_INCOMING)[:1000],
                method=(method or "POST")[:10],
                source_ip=(source_ip or "")[:64],
                idempotency_key=(idempotency_key or "")[:200],
                attempt=max(1, int(attempt or 1)),
                max_attempts=max(1, int(max_attempts or 1)),
                will_retry=bool(will_retry),
                status_code=status_code,
                duration_ms=int(duration_ms) if duration_ms is not None else None,
                detail=snippet(detail),
                response_snippet=snippet(response_snippet),
                request_payload=redact_payload(request_payload),
            )
            db.add(row)
            await db.flush()
            await db.commit()
            row_id = row.id

        now = time.monotonic()
        if now - _last_prune >= _PRUNE_INTERVAL_SECONDS:
            _last_prune = now
            retention = max(1, int(getattr(settings, "webhook_log_retention_days", 30)))
            await prune_webhook_logs(retention)
        return row_id
    except Exception as e:  # audit logging must never break webhook delivery
        logger.debug("Could not persist webhook log: %s", e)
        return None


async def prune_webhook_logs(older_than_days: int, tenant_id: Optional[int] = None) -> int:
    """Delete log rows older than ``older_than_days``; returns deleted count.

    When ``tenant_id`` is given, platform-level (null-tenant) rows are retained;
    only that tenant's expired rows are removed.
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(0, int(older_than_days)))
        stmt = delete(WebhookLog).where(WebhookLog.created_at < cutoff)
        if tenant_id is not None:
            stmt = stmt.where(WebhookLog.tenant_id == tenant_id)
        async with async_session_factory() as db:
            result = await db.execute(stmt)
            await db.commit()
            return int(result.rowcount or 0)
    except Exception as e:
        logger.debug("Could not prune webhook logs: %s", e)
        return 0


def serialize_log(row: WebhookLog, *, include_payload: bool = False) -> dict:
    """JSON-ready dict for the admin API (payload only on the detail route)."""
    result = {
        "id": row.id,
        "direction": row.direction,
        "event_type": row.event_type,
        "status": row.status,
        "success": row.success,
        "workflow_id": row.workflow_id,
        "run_id": row.run_id,
        "tenant_id": row.tenant_id,
        "endpoint": row.endpoint,
        "method": row.method,
        "source_ip": row.source_ip,
        "idempotency_key": row.idempotency_key,
        "attempt": row.attempt,
        "max_attempts": row.max_attempts,
        "will_retry": row.will_retry,
        "status_code": row.status_code,
        "duration_ms": row.duration_ms,
        "detail": row.detail,
        "response_snippet": row.response_snippet,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if include_payload:
        result["request_payload"] = row.request_payload
    return result
