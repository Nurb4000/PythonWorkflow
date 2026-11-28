"""External notification channels (Feature-gap G4).

In-app notifications (``app.services.notification_service``) only track a
read/unread badge for the UI. G4 adds *external* delivery so that events which
matter to a user -- SLA/OLA breaches, workflow failure, task assignment, ... --
are also pushed through pluggable channels:

* **Email**   -- reuses ``app.services.email_service`` (SMTP).
* **Slack**   -- POSTs a message to a Slack incoming-webhook URL.
* **Webhook** -- POSTs a signed JSON payload to an arbitrary endpoint
                 (HMAC-SHA256 signature in the ``X-Signature`` header).

Design notes
------------
* Each channel implements :class:`NotificationChannel` and is *best-effort*: a
  failing channel never aborts dispatch and never raises to the caller.
* Routing (which channels a given notification *type* uses) is data-driven with
  sane defaults in :data:`DEFAULT_ROUTING`; it can be overridden at runtime via
  the ``notification_channel_routing`` system setting (see
  ``notification_service.apply_routing``).
* Channels build their own HTTP client, but accept an injected one so tests can
  assert on the exact request without hitting the network.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import httpx

from app.core.config import settings
from app.services import webhook_log_service as webhook_logs
from app.services.outgoing_webhook import (
    OutgoingWebhookSender,
    WebhookAttempt,
    WebhookRequest,
)

logger = logging.getLogger(__name__)


def _as_int(value) -> Optional[int]:
    """Best-effort coercion for optional FK ids carried in notification context."""
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def _log_webhook_attempt(attempt: WebhookAttempt) -> None:
    """Persist one outbound delivery attempt (M4). Never raises."""
    ctx = attempt.context or {}
    status = (
        webhook_logs.STATUS_SUCCESS
        if attempt.success
        else (webhook_logs.STATUS_RETRY if attempt.will_retry else webhook_logs.STATUS_FAILED)
    )
    await webhook_logs.log_webhook_event(
        direction=webhook_logs.DIRECTION_OUTGOING,
        event_type=attempt.event_type,
        endpoint=attempt.url,
        success=attempt.success,
        status=status,
        workflow_id=_as_int(ctx.get("workflow_id")),
        run_id=_as_int(ctx.get("run_id")),
        tenant_id=_as_int(ctx.get("tenant_id")),
        idempotency_key=attempt.idempotency_key,
        attempt=attempt.attempt,
        max_attempts=attempt.max_attempts,
        will_retry=attempt.will_retry,
        status_code=attempt.status_code,
        duration_ms=attempt.duration_ms,
        detail=attempt.detail,
        response_snippet="" if attempt.success else attempt.detail,
        request_payload=attempt.payload,
    )


class NotificationType(str, Enum):
    """Notification categories. Mirrors the ``type`` column on ``notifications``."""

    TASK_ASSIGNED = "task_assigned"
    SLA_BREACH = "sla_breach"
    OLA_BREACH = "ola_breach"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    FORM_SUBMISSION = "form_submission"
    MENTION = "mention"
    # G7: operator-facing data-export events.
    EXPORT_CAP_REACHED = "export_cap_reached"
    EXPORT_RATE_LIMITED = "export_rate_limited"


class ChannelType(str, Enum):
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"


@dataclass
class DeliveryResult:
    """Outcome of delivering one notification to one recipient via one channel."""

    channel: str
    recipient: str
    ok: bool
    detail: str = ""


@dataclass
class NotificationTarget:
    """Everything a channel needs to deliver a notification externally."""

    type: str
    title: str
    message: str = ""
    recipients: list[str] = field(default_factory=list)
    context: dict = field(default_factory=dict)
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None

    def render_text(self) -> str:
        """Human-readable body (used by Slack / email)."""
        parts = [self.title]
        if self.message:
            parts.append(self.message)
        return "\n\n".join(parts)


# Default routing: which channel types each notification type should use. Channels
# are only used when additionally configured (``is_configured``), so enabling a
# channel is enough to start receiving its notifications.
DEFAULT_ROUTING: dict[str, list[str]] = {
    NotificationType.WORKFLOW_FAILED.value: [
        ChannelType.EMAIL.value,
        ChannelType.SLACK.value,
        ChannelType.WEBHOOK.value,
    ],
    NotificationType.SLA_BREACH.value: [
        ChannelType.EMAIL.value,
        ChannelType.SLACK.value,
        ChannelType.WEBHOOK.value,
    ],
    NotificationType.OLA_BREACH.value: [ChannelType.EMAIL.value, ChannelType.SLACK.value],
    NotificationType.TASK_ASSIGNED.value: [ChannelType.EMAIL.value],
    NotificationType.FORM_SUBMISSION.value: [ChannelType.EMAIL.value, ChannelType.WEBHOOK.value],
    NotificationType.WORKFLOW_COMPLETED.value: [ChannelType.EMAIL.value],
    NotificationType.MENTION.value: [ChannelType.EMAIL.value, ChannelType.SLACK.value],
    NotificationType.EXPORT_CAP_REACHED.value: [
        ChannelType.EMAIL.value,
        ChannelType.SLACK.value,
        ChannelType.WEBHOOK.value,
    ],
    NotificationType.EXPORT_RATE_LIMITED.value: [
        ChannelType.EMAIL.value,
        ChannelType.SLACK.value,
        ChannelType.WEBHOOK.value,
    ],
}


class NotificationChannel(ABC):
    """Base class for an external delivery channel."""

    type: ChannelType
    name: str = ""

    @abstractmethod
    async def is_configured(self) -> bool:
        """Whether this channel has what it needs to send."""

    @abstractmethod
    async def send(self, target: NotificationTarget) -> list[DeliveryResult]:
        """Deliver *target*; return one :class:`DeliveryResult` per recipient."""


class EmailChannel(NotificationChannel):
    """Deliver via SMTP using the existing email service."""

    type = ChannelType.EMAIL
    name = "Email"

    async def is_configured(self) -> bool:
        from app.services.email_service import smtp_diagnostics

        return bool(smtp_diagnostics().get("configured"))

    async def send(self, target: NotificationTarget) -> list[DeliveryResult]:
        from app.services.email_service import send_email

        results: list[DeliveryResult] = []
        body = target.render_text()
        for recipient in target.recipients:
            res = send_email(to=recipient, subject=target.title, body=body)
            ok = bool(res.get("sent"))
            if ok:
                detail = res.get("stage") or "ok"
            else:
                # Surface the real failure reason (e.g. "auth failed") rather than
                # just the SMTP stage, so misconfigured channels are diagnosable.
                detail = res.get("error") or res.get("stage") or "send failed"
            results.append(DeliveryResult(self.type.value, recipient, ok, detail))
        return results


class SlackChannel(NotificationChannel):
    """Deliver via a Slack incoming webhook."""

    type = ChannelType.SLACK
    name = "Slack"

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        # Injected for tests; production uses a fresh client per send.
        self._client = client

    async def is_configured(self) -> bool:
        return bool(settings.slack_webhook_url)

    async def _post(self, url: str, payload: dict, headers: dict) -> tuple[int, str]:
        async with (self._client or httpx.AsyncClient()) as client:
            resp = await client.post(
                url, content=json.dumps(payload).encode(), headers=headers, timeout=10
            )
        return resp.status_code, resp.text

    async def send(self, target: NotificationTarget) -> list[DeliveryResult]:
        url = settings.slack_webhook_url
        if not url:
            return [DeliveryResult(self.type.value, "<webhook>", False, "not configured")]
        text = f"**{target.title}**\n{target.message}".strip()
        payload = {
            "text": text,
            "metadata": {"type": target.type, **target.context},
        }
        try:
            status, body = await self._post(url, payload, {"Content-Type": "application/json"})
            ok = 200 <= status < 300
            detail = "ok" if ok else f"HTTP {status}: {body[:200]}"
            await webhook_logs.log_webhook_event(
                direction=webhook_logs.DIRECTION_OUTGOING,
                event_type=webhook_logs.EVENT_NOTIFICATION_SLACK,
                endpoint=url,
                success=ok,
                status=webhook_logs.STATUS_SUCCESS if ok else webhook_logs.STATUS_FAILED,
                status_code=status,
                attempt=1,
                max_attempts=1,
                detail=detail,
                response_snippet="" if ok else body[:200],
                request_payload=payload,
                workflow_id=_as_int(target.context.get("workflow_id")),
                run_id=_as_int(target.context.get("run_id")),
                tenant_id=_as_int(target.context.get("tenant_id")),
            )
            return [DeliveryResult(self.type.value, "<webhook>", ok, detail)]
        except Exception as e:  # best-effort: never raise to the caller
            detail = f"{type(e).__name__}: {e}"
            await webhook_logs.log_webhook_event(
                direction=webhook_logs.DIRECTION_OUTGOING,
                event_type=webhook_logs.EVENT_NOTIFICATION_SLACK,
                endpoint=url,
                success=False,
                status=webhook_logs.STATUS_FAILED,
                attempt=1,
                max_attempts=1,
                detail=detail,
                request_payload=payload,
                workflow_id=_as_int(target.context.get("workflow_id")),
                run_id=_as_int(target.context.get("run_id")),
                tenant_id=_as_int(target.context.get("tenant_id")),
            )
            return [DeliveryResult(self.type.value, "<webhook>", False, detail)]


class WebhookChannel(NotificationChannel):
    """Deliver a signed JSON payload to an arbitrary HTTP endpoint."""

    type = ChannelType.WEBHOOK
    name = "Webhook"

    def __init__(
        self,
        client: Optional[httpx.AsyncClient] = None,
        max_retries: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 30.0,
    ) -> None:
        # Delegates signing + retry-with-backoff + idempotency to the shared
        # OutgoingWebhookSender (G5). The injected client is threaded through for tests.
        self._sender = OutgoingWebhookSender(
            client=client,
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
        )

    async def is_configured(self) -> bool:
        return bool(settings.webhook_url)

    async def send(self, target: NotificationTarget) -> list[DeliveryResult]:
        url = settings.webhook_url
        if not url:
            return [DeliveryResult(self.type.value, "<webhook>", False, "not configured")]
        payload = {
            "type": target.type,
            "title": target.title,
            "message": target.message,
            "recipients": target.recipients,
            "context": target.context,
            "entity": (
                {"type": target.entity_type, "id": target.entity_id}
                if target.entity_type
                else None
            ),
        }
        # A single logical delivery carries one idempotency key + signature across all
        # retry attempts, so transient failures don't cause duplicate processing.
        # Each attempt is written to the M4 execution log via the callback.
        result = await self._sender.deliver(
            WebhookRequest(
                url=url,
                payload=payload,
                secret=settings.webhook_secret,
                attempt_logger=_log_webhook_attempt,
                log_event_type=webhook_logs.EVENT_NOTIFICATION_WEBHOOK,
                log_context=dict(target.context),
            )
        )
        return [DeliveryResult(self.type.value, "<webhook>", result.success, result.detail)]


class NotificationDispatcher:
    """Routes notifications to configured channels and aggregates results.

    Dispatch is best-effort: a channel that raises or misbehaves is recorded as a
    failed result but does not prevent the remaining channels from running.
    """

    def __init__(self, routing: Optional[dict[str, list[str]]] = None) -> None:
        self.routing: dict[str, list[str]] = routing or dict(DEFAULT_ROUTING)
        self._channels: dict[ChannelType, NotificationChannel] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register(EmailChannel())
        self.register(SlackChannel())
        self.register(WebhookChannel())

    def register(self, channel: NotificationChannel) -> NotificationChannel:
        """Register/replace a channel by its :class:`ChannelType`."""
        self._channels[channel.type] = channel
        return channel

    def get(self, channel_type: ChannelType | str) -> Optional[NotificationChannel]:
        key = channel_type if isinstance(channel_type, ChannelType) else ChannelType(channel_type)
        return self._channels.get(key)

    async def configured_channels_for(self, ntype: str) -> list[NotificationChannel]:
        channels: list[NotificationChannel] = []
        for ctype in self.routing.get(ntype, []):
            channel = self.get(ctype)
            if channel is not None and await channel.is_configured():
                channels.append(channel)
        return channels

    async def dispatch(self, target: NotificationTarget) -> dict[str, list[DeliveryResult]]:
        """Send *target* through every configured channel for its type."""
        results: dict[str, list[DeliveryResult]] = {}
        try:
            channels = await self.configured_channels_for(target.type)
        except Exception as e:  # routing config error should not break delivery
            logger.error("Error resolving channels for %s: %s", target.type, e)
            channels = []

        for channel in channels:
            try:
                results[channel.type.value] = await channel.send(target)
            except Exception as e:
                logger.error(
                    "Channel %s failed for %s: %s", channel.type, target.type, e
                )
                results[channel.type.value] = [
                    DeliveryResult(channel.type.value, "<all>", False, f"{type(e).__name__}: {e}")
                ]
        return results

    def reset(self) -> None:
        """Restore default channels (used by tests)."""
        self._channels.clear()
        self._register_defaults()


# Process-wide dispatcher used by the app. Tests build their own instance.
notification_dispatcher = NotificationDispatcher()
