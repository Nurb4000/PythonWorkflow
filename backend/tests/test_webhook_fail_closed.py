"""
Regression tests for findings #30: POST /webhook/{workflow_id} must fail closed
when no webhook secret is configured.

Previously ``verify_webhook_secret()`` returned immediately when WEBHOOK_SECRET
was empty, so anyone who knew a workflow_id could trigger any active workflow
anonymously — including ``custom_code`` steps (finding #1, OS command execution)
or network/DB steps (exfiltration, SSRF, DoS). The function now raises 401 unless
a secret is configured and matches.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import webhooks


def _set_secret(monkeypatch, value):
    monkeypatch.setattr(webhooks.settings, "webhook_secret", value)


# --------------------------------------------------------------------------- #
# Part A: verify_webhook_secret unit behavior
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("secret,presented,expected", [
    ("", None, 401),         # fail closed: unconfigured
    ("", "whatever", 401),   # fail closed even with a presented secret
    ("s3cret", None, 401),   # configured but header missing
    ("s3cret", "nope", 403), # configured but wrong
    ("s3cret", "s3cret", None),  # configured and correct -> passes
])
def test_verify_webhook_secret(monkeypatch, secret, presented, expected):
    from fastapi import HTTPException
    _set_secret(monkeypatch, secret)
    if expected is None:
        webhooks.verify_webhook_secret(presented)  # must not raise
    else:
        with pytest.raises(HTTPException) as exc:
            webhooks.verify_webhook_secret(presented)
        assert exc.value.status_code == expected


# --------------------------------------------------------------------------- #
# Part B: endpoint-level integration (fail closed + accept correct secret)
# --------------------------------------------------------------------------- #
@pytest.fixture
def app(monkeypatch):
    class _Run:
        id = 99

    class _Workflow:
        id = 5

    class _Result:
        def scalar_one_or_none(self):
            return _Workflow()

    class _FakeDB:
        async def execute(self, stmt):  # noqa: ARG003 - statement ignored
            return _Result()

    async def fake_trigger(wid, payload):  # endpoint awaits this, so it must be async
        return _Run()

    monkeypatch.setattr(webhooks.scheduler_service, "trigger_webhook", fake_trigger)
    application = FastAPI()
    application.include_router(webhooks.router)
    application.dependency_overrides.clear()
    application.dependency_overrides[webhooks.get_db] = lambda: _FakeDB()
    return application


def test_endpoint_fails_closed_when_secret_unset(app, monkeypatch):
    _set_secret(monkeypatch, "")
    client = TestClient(app)
    resp = client.post("/webhook/5", json={"x": 1},
                       headers={"X-Webhook-Secret": "s3cret"})
    assert resp.status_code == 401
    assert "not configured" in resp.json()["detail"].lower()


def test_endpoint_accepts_correct_secret(app, monkeypatch):
    _set_secret(monkeypatch, "s3cret")
    client = TestClient(app)
    resp = client.post("/webhook/5", json={"x": 1},
                       headers={"X-Webhook-Secret": "s3cret"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_endpoint_rejects_wrong_secret(app, monkeypatch):
    _set_secret(monkeypatch, "s3cret")
    client = TestClient(app)
    resp = client.post("/webhook/5", json={"x": 1},
                       headers={"X-Webhook-Secret": "wrong"})
    assert resp.status_code == 403
