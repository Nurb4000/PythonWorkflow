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

import hashlib
import hmac
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class NotificationType(str, Enum):
    """Notification categories. Mirrors the ``type`` column on ``notifications``."""

    TASK_ASSIGNED = "task_assigned"
    SLA_BREACH = "sla_breach"
    OLA_BREACH = "ola_breach"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    FORM_SUBMISSION = "form_submission"
    MENTION = "mention"


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
            return [DeliveryResult(self.type.value, "<webhook>", ok, detail)]
        except Exception as e:  # best-effort: never raise to the caller
            return [DeliveryResult(self.type.value, "<webhook>", False, f"{type(e).__name__}: {e}")]


class WebhookChannel(NotificationChannel):
    """Deliver a signed JSON payload to an arbitrary HTTP endpoint."""

    type = ChannelType.WEBHOOK
    name = "Webhook"

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        self._client = client

    async def is_configured(self) -> bool:
        return bool(settings.webhook_url)

    async def _sign(self, body: bytes) -> Optional[str]:
        secret = settings.webhook_secret
        if not secret:
            return None
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    async def _post(self, url: str, payload: dict, headers: dict) -> tuple[int, str]:
        async with (self._client or httpx.AsyncClient()) as client:
            resp = await client.post(
                url, content=json.dumps(payload).encode(), headers=headers, timeout=10
            )
        return resp.status_code, resp.text

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
        body = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        signature = await self._sign(body)
        if signature:
            headers["X-Signature"] = signature
        try:
            status, resp_body = await self._post(url, payload, headers)
            ok = 200 <= status < 300
            detail = "ok" if ok else f"HTTP {status}: {resp_body[:200]}"
            return [DeliveryResult(self.type.value, "<webhook>", ok, detail)]
        except Exception as e:  # best-effort: never raise to the caller
            return [DeliveryResult(self.type.value, "<webhook>", False, f"{type(e).__name__}: {e}")]


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
