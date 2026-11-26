"""Tests for G5: outgoing webhook signing + retry/idempotency.

Covers the reusable ``OutgoingWebhookSender`` and its ``sign_payload`` helper:

* HMAC-SHA256 signing (``X-Signature: sha256=<hex>``), absent when no secret.
* Retry with exponential backoff on transient failures (5xx / 429 / 408 / network
  errors), succeeding once the endpoint recovers.
* Give-up after ``max_retries`` with a clear failure result.
* No retry on non-retryable client errors (4xx other than 408).
* A stable per-request ``X-Idempotency-Key`` across all retry attempts, and a
  caller-supplied key used verbatim.

No test hits the network: an injected fake ``httpx.AsyncClient`` records requests
and returns queued responses (or raises queued exceptions). Backoff uses
``base_delay=0`` so retries are instant.
"""
import hashlib
import hmac

import httpx
import pytest

from app.services.outgoing_webhook import (
    OutgoingWebhookSender,
    WebhookRequest,
    WebhookResult,
    sign_payload,
)


# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #
class FakeResponse:
    def __init__(self, status_code=200, text="ok"):
        self.status_code = status_code
        self.text = text


class FakeAsyncClient:
    """Records posts; returns queued (status, text) pairs or raises queued exceptions."""

    def __init__(self, responses=None):
        self.responses = list(responses) if responses is not None else [FakeResponse(200, "ok")]
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, *, content=None, headers=None, timeout=None):
        self.requests.append(
            {"url": url, "content": content, "headers": headers, "timeout": timeout}
        )
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, FakeResponse):
            return item
        status, text = item
        return FakeResponse(status, text)


def _sender(client, **kw):
    """Sender with base_delay=0 so retry backoff is instant in tests."""
    return OutgoingWebhookSender(client=client, base_delay=0.0, **kw)


def _req(**kw):
    base = dict(url="https://example.com/hook", payload={"hello": "world"}, secret="s3cret")
    base.update(kw)
    return WebhookRequest(**base)


def _expected_signature(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# --------------------------------------------------------------------------- #
# Signing
# --------------------------------------------------------------------------- #
def test_sign_payload_is_sha256_hmac():
    body = b'{"a": 1}'
    sig = sign_payload(body, "secret")
    assert sig == _expected_signature(body, "secret")
    assert sig.startswith("sha256=")


def test_sign_payload_none_when_no_secret():
    assert sign_payload(b"{}", "") is None


@pytest.mark.parametrize(
    "code,expected",
    [
        (200, False),
        (201, False),
        (302, False),
        (400, False),
        (401, False),
        (404, False),
        (408, True),
        (429, True),
        (500, True),
        (503, True),
        (599, True),
    ],
)
def test_is_retryable_status(code, expected):
    assert OutgoingWebhookSender.is_retryable_status(code) is expected


# --------------------------------------------------------------------------- #
# Success + headers
# --------------------------------------------------------------------------- #
async def test_deliver_succeeds_first_attempt_with_signature_and_idempotency():
    client = FakeAsyncClient([(201, "created")])
    result = await _sender(client).deliver(_req())

    assert result.success is True
    assert result.status_code == 201
    assert result.attempt == 1
    assert result.signature == _expected_signature(b'{"hello": "world"}', "s3cret")
    assert result.idempotency_key  # a key was minted

    req = client.requests[0]
    assert req["headers"]["X-Signature"] == result.signature
    assert req["headers"]["X-Idempotency-Key"] == result.idempotency_key


async def test_custom_idempotency_key_used_verbatim():
    client = FakeAsyncClient([(200, "ok")])
    result = await _sender(client).deliver(_req(idempotency_key="order-42"))
    assert result.idempotency_key == "order-42"
    assert client.requests[0]["headers"]["X-Idempotency-Key"] == "order-42"


async def test_no_signature_header_when_no_secret():
    client = FakeAsyncClient([(200, "ok")])
    result = await _sender(client).deliver(_req(secret=""))
    assert result.success is True
    assert result.signature is None
    assert "X-Signature" not in client.requests[0]["headers"]


# --------------------------------------------------------------------------- #
# Retry semantics
# --------------------------------------------------------------------------- #
async def test_retries_on_5xx_then_succeeds():
    client = FakeAsyncClient([(503, "unavailable"), (503, "unavailable"), (200, "ok")])
    result = await _sender(client).deliver(_req(max_retries=3))

    assert result.success is True
    assert result.attempt == 3
    # Idempotency key is identical across every attempt so the receiver can dedupe.
    keys = {r["headers"]["X-Idempotency-Key"] for r in client.requests}
    assert len(keys) == 1
    assert result.idempotency_key in keys


async def test_retries_on_transport_error_then_succeeds():
    client = FakeAsyncClient(
        [
            httpx.ConnectError("boom"),
            httpx.ConnectError("boom"),
            FakeResponse(200, "ok"),
        ]
    )
    result = await _sender(client).deliver(_req(max_retries=3))

    assert result.success is True
    assert result.attempt == 3
    assert len(client.requests) == 3


async def test_gives_up_after_max_retries_on_persistent_5xx():
    client = FakeAsyncClient([(503, "svc down")] * 5)
    result = await _sender(client).deliver(_req(max_retries=3))

    assert result.success is False
    assert result.status_code == 503
    assert result.attempt == 3
    # Exactly max_retries attempts were made -- no wasted calls beyond that.
    assert len(client.requests) == 3


async def test_does_not_retry_on_non_retryable_4xx():
    client = FakeAsyncClient([(404, "not found")])
    result = await _sender(client).deliver(_req(max_retries=5))

    assert result.success is False
    assert result.status_code == 404
    assert result.attempt == 1
    assert len(client.requests) == 1  # failed fast, no retries


async def test_429_is_retried():
    client = FakeAsyncClient([(429, "slow down"), (200, "ok")])
    result = await _sender(client).deliver(_req(max_retries=3))
    assert result.success is True
    assert result.attempt == 2


async def test_network_error_exhausts_retries():
    client = FakeAsyncClient([httpx.ConnectError("down")] * 5)
    result = await _sender(client).deliver(_req(max_retries=2))
    assert result.success is False
    assert result.status_code is None
    assert result.attempt == 2
    assert len(client.requests) == 2


async def test_backoff_delay_is_exponential_and_capped():
    s = OutgoingWebhookSender(base_delay=1.0, max_delay=8.0, jitter=False)
    # Full jitter disabled -> deterministic exponential cap.
    assert s._backoff_delay(1) == 1.0
    assert s._backoff_delay(2) == 2.0
    assert s._backoff_delay(3) == 4.0
    assert s._backoff_delay(4) == 8.0  # capped
    assert s._backoff_delay(10) == 8.0  # still capped


async def test_jitter_stays_within_bounds():
    s = OutgoingWebhookSender(base_delay=2.0, max_delay=100.0, jitter=True)
    for _ in range(50):
        d = s._backoff_delay(1)
        assert 0.0 <= d <= 2.0
