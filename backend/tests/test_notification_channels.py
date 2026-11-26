"""Tests for G4 external notification channels.

Covers the pluggable channel abstraction (Email / Slack / signed Webhook), the
best-effort :class:`NotificationDispatcher` routing, and the
``notification_service.notify`` / ``notify_admins`` entry points that wire those
channels into in-app notifications.

No test hits the network: Slack/Webhook channels accept an injected fake
``httpx.AsyncClient`` (records requests, returns a canned response), and Email
reuses the real ``email_service`` with ``send_email`` monkeypatched. Settings are
forced via ``object.__setattr__`` because pydantic-settings ignores plain
assignment.
"""
import hashlib
import hmac
import json

import pytest

from app.core.config import settings
from app.services.notification_channels import (
    ChannelType,
    DeliveryResult,
    NotificationChannel,
    NotificationDispatcher,
    NotificationTarget,
)


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #
class FakeResponse:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text


class FakeAsyncClient:
    """Stand-in for httpx.AsyncClient: async context manager + records posts."""

    def __init__(self, response=None):
        self._response = response or FakeResponse(200, "ok")
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, *, content=None, headers=None, timeout=None):
        self.requests.append(
            {"url": url, "content": content, "headers": headers, "timeout": timeout}
        )
        return self._response


class FakeChannel(NotificationChannel):
    """Configurable channel for dispatcher tests."""

    def __init__(self, ctype, configured=True):
        self.type = ctype
        self._configured = configured
        self.sent = []

    async def is_configured(self):
        return self._configured

    async def send(self, target):
        self.sent.append(target)
        return [DeliveryResult(self.type.value, "fake@x", self._configured)]


def _target(**kw):
    base = dict(type="workflow_failed", title="Boom", message="it failed")
    base.update(kw)
    return NotificationTarget(**base)


def _set(name, value):
    """Force a settings attribute (pydantic-settings ignores plain assignment)."""
    saved = getattr(settings, name)
    object.__setattr__(settings, name, value)
    return saved


# --------------------------------------------------------------------------- #
# Email channel
# --------------------------------------------------------------------------- #
async def test_email_channel_builds_and_reports(monkeypatch):
    from app.services import email_service
    from app.services.notification_channels import EmailChannel

    calls = {}

    def fake_send(to, subject, body, **kw):
        calls.update(to=to, subject=subject, body=body)
        return {"sent": True, "stage": None}

    monkeypatch.setattr(email_service, "send_email", fake_send)

    res = await EmailChannel().send(_target(recipients=["a@x.com", "b@x.com"]))
    assert len(res) == 2
    assert all(r.ok for r in res)
    assert {r.recipient for r in res} == {"a@x.com", "b@x.com"}
    assert calls["subject"] == "Boom"
    assert "it failed" in calls["body"]


async def test_email_channel_reports_failure(monkeypatch):
    from app.services.notification_channels import EmailChannel

    def fake_send(to, subject, body, **kw):
        return {"sent": False, "stage": "send", "error": "auth failed"}

    monkeypatch.setattr("app.services.email_service.send_email", fake_send)
    res = await EmailChannel().send(_target(recipients=["a@x.com"]))
    assert res[0].ok is False
    assert "auth failed" in res[0].detail


async def test_email_is_configured(monkeypatch):
    from app.services.notification_channels import EmailChannel

    monkeypatch.setattr(
        "app.services.email_service.smtp_diagnostics", lambda: {"configured": True}
    )
    assert await EmailChannel().is_configured() is True
    monkeypatch.setattr(
        "app.services.email_service.smtp_diagnostics", lambda: {"configured": False}
    )
    assert await EmailChannel().is_configured() is False


# --------------------------------------------------------------------------- #
# Slack channel
# --------------------------------------------------------------------------- #
async def test_slack_channel_posts_payload():
    from app.services.notification_channels import SlackChannel

    client = FakeAsyncClient(FakeResponse(200, "ok"))
    saved = _set("slack_webhook_url", "https://slack.com/api/webhook")
    try:
        res = await SlackChannel(client=client).send(_target(message="down"))
        assert res[0].ok
        req = client.requests[0]
        payload = json.loads(req["content"])
        assert payload["text"].startswith("**Boom**")
        assert payload["metadata"]["type"] == "workflow_failed"
        assert req["headers"]["Content-Type"] == "application/json"
    finally:
        _set("slack_webhook_url", saved)


async def test_slack_not_configured():
    from app.services.notification_channels import SlackChannel

    saved = _set("slack_webhook_url", "")
    try:
        res = await SlackChannel(client=FakeAsyncClient()).send(_target())
        assert not res[0].ok
        assert "not configured" in res[0].detail
    finally:
        _set("slack_webhook_url", saved)


async def test_slack_http_error_reported():
    from app.services.notification_channels import SlackChannel

    client = FakeAsyncClient(FakeResponse(500, "boom"))
    saved = _set("slack_webhook_url", "https://slack.com/api/webhook")
    try:
        res = await SlackChannel(client=client).send(_target())
        assert not res[0].ok
        assert "500" in res[0].detail
    finally:
        _set("slack_webhook_url", saved)


# --------------------------------------------------------------------------- #
# Webhook channel (HMAC signing)
# --------------------------------------------------------------------------- #
async def test_webhook_channel_signs_payload():
    from app.services.notification_channels import WebhookChannel

    client = FakeAsyncClient(FakeResponse(201, "created"))
    saved_url = _set("webhook_url", "https://example.com/hook")
    saved_secret = _set("webhook_secret", "s3cret")
    try:
        res = await WebhookChannel(client=client).send(
            _target(recipients=["a@x.com"], entity_type="workflow_run", entity_id=42)
        )
        assert res[0].ok
        req = client.requests[0]
        payload = json.loads(req["content"])
        assert payload["type"] == "workflow_failed"
        assert payload["recipients"] == ["a@x.com"]
        assert payload["entity"] == {"type": "workflow_run", "id": 42}
        expected = "sha256=" + hmac.new(
            b"s3cret", req["content"], hashlib.sha256
        ).hexdigest()
        assert req["headers"]["X-Signature"] == expected
    finally:
        _set("webhook_url", saved_url)
        _set("webhook_secret", saved_secret)


async def test_webhook_no_signature_when_no_secret():
    from app.services.notification_channels import WebhookChannel

    client = FakeAsyncClient(FakeResponse(200, "ok"))
    saved_url = _set("webhook_url", "https://example.com/hook")
    saved_secret = _set("webhook_secret", "")
    try:
        await WebhookChannel(client=client).send(_target())
        assert "X-Signature" not in client.requests[0]["headers"]
    finally:
        _set("webhook_url", saved_url)
        _set("webhook_secret", saved_secret)


async def test_webhook_not_configured():
    from app.services.notification_channels import WebhookChannel

    saved = _set("webhook_url", "")
    try:
        res = await WebhookChannel(client=FakeAsyncClient()).send(_target())
        assert not res[0].ok
        assert "not configured" in res[0].detail
    finally:
        _set("webhook_url", saved)


# --------------------------------------------------------------------------- #
# Dispatcher routing / best-effort semantics
# --------------------------------------------------------------------------- #
def test_dispatcher_registers_default_channels():
    d = NotificationDispatcher()
    assert d.get(ChannelType.EMAIL) is not None
    assert d.get(ChannelType.SLACK) is not None
    assert d.get(ChannelType.WEBHOOK) is not None


async def test_dispatcher_only_sends_configured():
    d = NotificationDispatcher(routing={"workflow_failed": ["email", "slack"]})
    email = FakeChannel(ChannelType.EMAIL, configured=True)
    slack = FakeChannel(ChannelType.SLACK, configured=False)
    d.register(email)
    d.register(slack)

    results = await d.dispatch(_target())
    assert "email" in results
    assert "slack" not in results
    assert len(email.sent) == 1


async def test_dispatcher_respects_custom_routing():
    d = NotificationDispatcher(routing={"task_assigned": ["slack"]})
    slack = FakeChannel(ChannelType.SLACK, configured=True)
    d.register(slack)

    await d.dispatch(_target(type="task_assigned"))
    assert len(slack.sent) == 1


async def test_dispatcher_best_effort_on_error():
    class BoomChannel(NotificationChannel):
        type = ChannelType.WEBHOOK

        async def is_configured(self):
            return True

        async def send(self, target):
            raise RuntimeError("boom")

    d = NotificationDispatcher(routing={"workflow_failed": ["email", "webhook"]})
    email = FakeChannel(ChannelType.EMAIL, configured=True)
    d.register(email)
    d.register(BoomChannel())

    results = await d.dispatch(_target())
    assert len(email.sent) == 1  # email still delivered despite webhook raising
    assert results["webhook"][0].ok is False


# --------------------------------------------------------------------------- #
# notify() / notify_admins() entry points
# --------------------------------------------------------------------------- #
async def test_notify_admins_builds_target_with_admin_recipient(monkeypatch):
    from app.services import notification_service as ns

    captured = {}

    async def fake_dispatch(target):
        captured["target"] = target
        return {}

    saved = _set("admin_notify_email", "admin@x.com")
    try:
        monkeypatch.setattr(ns.notification_dispatcher, "dispatch", fake_dispatch)
        await ns.notify_admins(type="sla_breach", title="Breach", message="x")
        assert captured["target"].recipients == ["admin@x.com"]
        assert captured["target"].type == "sla_breach"
    finally:
        _set("admin_notify_email", saved)


async def test_notify_creates_inapp_and_dispatches(db_session, monkeypatch):
    from app.models.auth import User
    from app.services import notification_service as ns

    # Persist a real user so the notification's FK to users resolves. Flush to
    # obtain the server-assigned id, which we then mirror on the stub principal
    # passed to notify() (notify only reads .id / .email off the principal).
    user_row = User(
        username="assignee_test",
        email="assignee@x.com",
        password_hash="sha256:stub",
        role="user",
    )
    db_session.add(user_row)
    await db_session.flush()
    user_id = user_row.id

    captured = {}

    async def fake_dispatch(target):
        captured["target"] = target
        return {"email": []}

    user = type("U", (), {"id": user_id, "email": user_row.email})()
    monkeypatch.setattr(ns.notification_dispatcher, "dispatch", fake_dispatch)

    notification, results = await ns.notify(
        db_session,
        user,
        type="task_assigned",
        title="Task assigned: X",
        related_entity_type="task",
        related_entity_id=99,
    )

    # In-app row persisted.
    assert notification.id is not None
    assert notification.user_id == user_id
    assert notification.type == "task_assigned"
    # External target built from the user's email.
    assert captured["target"].recipients == [user_row.email]
    assert captured["target"].entity_id == 99
    await db_session.commit()
