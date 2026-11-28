"""G7: operator alerts for data-export cap and rate-limit events.

The data-export endpoints are high-cost table dumps. M5 bounded their frequency
and a hard 100k-row cap bounds their size, but neither event was visible to
operators. This module pushes both events through the existing G4 admin
notification channels (email / Slack / signed webhook), reusing
``notify_admins`` so no new table, model or migration is required.

Design rules:

* Best-effort only -- an alert failure must never change the export response or
  turn a 429 into a 500. ``notify_admins`` is already best-effort and this module
  additionally guards the call.
* No payload data is logged: only the allow-listed table name, limits, row count,
  user id, client IP and path are included. Query filters/values never leave the
  server through this path.
* Events are deduped per table/user (cap) or per IP/path (rate limit) for
  ``settings.export_alert_cooldown_seconds`` so a repeat offender cannot spam
  the configured channels.
"""
import logging
import time
from typing import Any, Optional

from app.core.config import settings
from app.services.notification_channels import NotificationType
from app.services.notification_service import notify_admins

logger = logging.getLogger(__name__)

# Hard ceiling on rows returned by /data-export/* (already enforced by the
# endpoints). Kept here so the alert and the enforcement cannot drift.
EXPORT_ROW_CAP = 100000


class _AlertCooldown:
    """Small in-memory dedupe window for repeated alert events."""

    def __init__(self) -> None:
        self._last: dict[str, float] = {}

    def allow(self, key: str) -> bool:
        seconds = max(0, int(getattr(settings, "export_alert_cooldown_seconds", 300)))
        if seconds == 0:
            return True
        now = time.monotonic()
        previous = self._last.get(key)
        if previous is not None and now - previous < seconds:
            return False
        self._last[key] = now
        return True

    def reset(self) -> None:
        self._last.clear()


export_alert_cooldown = _AlertCooldown()


async def _dispatch(event_type: str, title: str, message: str, context: dict) -> bool:
    """Send one admin alert; return True only when it was actually dispatched."""
    if not getattr(settings, "export_alerts_enabled", True):
        return False
    try:
        await notify_admins(type=event_type, title=title, message=message, context=context)
    except Exception:
        # Notification channels are best-effort by contract; never let an alert
        # failure affect the export or rate-limit response.
        logger.exception("Failed to dispatch %s export alert", event_type)
        return False
    return True


async def alert_export_cap(
    *,
    table: str,
    requested_limit: Optional[int] = None,
    applied_limit: Optional[int] = None,
    row_count: Optional[int] = None,
    user_id: Optional[int] = None,
    client_ip: Optional[str] = None,
    path: Optional[str] = None,
) -> bool:
    """Alert once when an export reaches or requests the 100k-row cap.

    Returns True when this call emitted an alert (False when deduped, disabled,
    or dispatch failed), so callers can avoid a second alert for the same event.
    """
    key = f"cap:{table}:{user_id or 'anonymous'}"
    if not export_alert_cooldown.allow(key):
        return False

    context: dict[str, Any] = {
        "event": NotificationType.EXPORT_CAP_REACHED.value,
        "table": table,
        "requested_limit": requested_limit,
        "applied_limit": applied_limit,
        "row_count": row_count,
        "user_id": user_id,
        "client_ip": client_ip,
        "path": path,
    }
    message = (
        f"table={table}; requested={requested_limit}; applied={applied_limit}; "
        f"rows={row_count}; user_id={user_id}; client_ip={client_ip}"
    )
    return await _dispatch(
        NotificationType.EXPORT_CAP_REACHED.value,
        "Data export reached the row cap",
        message,
        context,
    )


async def alert_export_rate_limited(
    *,
    client_ip: Optional[str] = None,
    path: Optional[str] = None,
    retry_after: Optional[int] = None,
    limit: Optional[int] = None,
    window_seconds: Optional[int] = None,
) -> bool:
    """Alert once when a client is throttled on a data-export endpoint."""
    key = f"rate:{client_ip or 'unknown'}:{path or '/data-export'}"
    if not export_alert_cooldown.allow(key):
        return False

    context: dict[str, Any] = {
        "event": NotificationType.EXPORT_RATE_LIMITED.value,
        "client_ip": client_ip,
        "path": path,
        "retry_after": retry_after,
        "limit": limit,
        "window_seconds": window_seconds,
    }
    message = (
        f"client_ip={client_ip}; path={path}; retry_after={retry_after}s; "
        f"limit={limit}/{window_seconds}s"
    )
    return await _dispatch(
        NotificationType.EXPORT_RATE_LIMITED.value,
        "Data export rate limit hit",
        message,
        context,
    )
