"""Outgoing webhook delivery: HMAC signing + retry with backoff + idempotency (G5).

When the app pushes a webhook *out* to an external endpoint, the receiver needs
three guarantees that a naive single ``httpx.post`` does not provide:

1. **Authenticity** -- the payload is signed with an HMAC-SHA256 so the receiver
   can verify it really came from us (and was not tampered with in transit).
2. **Reliability** -- transient failures (timeouts, transport errors, 5xx and
   ``429`` responses) are retried with exponential backoff + full jitter instead
   of failing on the first hiccup.
3. **Idempotency** -- every delivery carries a stable per-request
   ``X-Idempotency-Key`` header so that retries (and receiver-side at-least-once
   delivery) do not cause duplicate processing on the far end.

This is intentionally transport-agnostic: it is used by the G4 ``WebhookChannel``
for notification webhooks, but nothing here is specific to notifications.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

import httpx

logger = logging.getLogger(__name__)

# Delivery knobs. Retry/backoff are constructor-injectable (with sane defaults)
# rather than admin-configured: the point is robust delivery, not tuning knobs.
DEFAULT_TIMEOUT: float = 10.0
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_BASE_DELAY: float = 0.5  # seconds
DEFAULT_MAX_DELAY: float = 30.0  # seconds cap on any single backoff


def sign_payload(body: bytes, secret: str) -> Optional[str]:
    """Return an ``X-Signature`` value for *body*, or ``None`` when no secret.

    Format is ``sha256=<hex>`` so a receiver can recompute ``hmac(secret, body)``
    and compare with ``hmac.compare_digest`` (constant-time).
    """
    if not secret:
        return None
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def make_idempotency_key(key: Optional[str]) -> str:
    """Use the supplied key verbatim, or mint a fresh UUID4 when omitted."""
    return key or uuid.uuid4().hex


@dataclass
class WebhookAttempt:
    """One HTTP attempt within a delivery (M4 execution log).

    Emitted after every attempt -- including attempts that will be retried --
    so operators can see the full retry chain, not just the final outcome.
    """

    url: str
    payload: dict[str, Any]
    attempt: int
    max_attempts: int
    success: bool
    status_code: Optional[int]
    detail: str
    will_retry: bool
    duration_ms: int
    idempotency_key: str
    event_type: str = "outgoing_webhook"
    context: dict[str, Any] = field(default_factory=dict)


# Optional hook for writing the M4 execution log. Kept as a callback (rather
# than importing the log service here) so delivery stays transport-agnostic and
# existing callers/tests need no DB.
AttemptLogger = Optional[Callable[[WebhookAttempt], Awaitable[None]]]


@dataclass
class WebhookRequest:
    """A single signed, idempotent outgoing webhook delivery.

    ``max_retries`` is an optional per-request override; when ``None`` the sender's
    own retry policy (see :class:`OutgoingWebhookSender`) applies.
    """

    url: str
    payload: dict[str, Any]
    secret: str = ""
    idempotency_key: Optional[str] = None
    timeout: float = DEFAULT_TIMEOUT
    max_retries: Optional[int] = None
    attempt_logger: AttemptLogger = None
    log_event_type: str = "outgoing_webhook"
    log_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class WebhookResult:
    """Outcome of attempting to deliver a :class:`WebhookRequest`."""

    success: bool
    status_code: Optional[int]
    attempt: int
    idempotency_key: str
    signature: Optional[str]
    detail: str


class OutgoingWebhookSender:
    """Deliver signed webhooks with retry + idempotency.

    Inject a fake ``client`` (any object supporting the async-context-manager
    ``httpx.AsyncClient`` interface) in tests to assert on the exact request
    without hitting the network.
    """

    def __init__(
        self,
        client: Optional[Any] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay: float = DEFAULT_BASE_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        jitter: bool = True,
    ) -> None:
        self._client = client
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._jitter = jitter

    @staticmethod
    def is_retryable_status(code: int) -> bool:
        """Retry on server-side / overload / request-timeout status codes."""
        return code == 408 or code == 429 or 500 <= code < 600

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff with full jitter (AWS 'FullJitter' strategy)."""
        # attempt is 1-based; cap the exponential term to avoid overflow.
        exp = min(self._max_delay, self._base_delay * (2 ** (attempt - 1)))
        if not self._jitter:
            return exp
        # Full jitter: sleep a random value in [0, exp]. Keeps total wait bounded
        # while still desynchronizing concurrent producers hitting the same endpoint.
        return random.uniform(0, exp)

    async def deliver(self, request: WebhookRequest) -> WebhookResult:
        """Deliver *request*, retrying transient failures up to the effective cap.

        The effective cap is the per-request ``max_retries`` when set, otherwise the
        sender's configured default -- so a channel can set a policy once and callers
        may still override it for a single delivery. Every attempt is reported to
        ``request.attempt_logger`` when one is supplied (M4 execution log).
        """
        max_retries = request.max_retries if request.max_retries is not None else self._max_retries
        max_retries = max(1, max_retries)
        idem_key = make_idempotency_key(request.idempotency_key)
        body = json.dumps(request.payload).encode()
        signature = sign_payload(body, request.secret)

        # Headers are built once so the idempotency key + signature are identical
        # across every retry -- that is what makes the key meaningful to the receiver.
        headers = {"Content-Type": "application/json", "X-Idempotency-Key": idem_key}
        if signature:
            headers["X-Signature"] = signature

        async def note(
            attempt: int,
            started: float,
            success: bool,
            status_code: Optional[int],
            detail: str,
            will_retry: bool,
        ) -> None:
            """Record one attempt; a broken logger must not affect delivery."""
            if request.attempt_logger is None:
                return
            try:
                await request.attempt_logger(
                    WebhookAttempt(
                        url=request.url,
                        payload=request.payload,
                        attempt=attempt,
                        max_attempts=max_retries,
                        success=success,
                        status_code=status_code,
                        detail=detail,
                        will_retry=will_retry,
                        duration_ms=int((time.monotonic() - started) * 1000),
                        idempotency_key=idem_key,
                        event_type=request.log_event_type,
                        context=request.log_context,
                    )
                )
            except Exception as e:  # audit logging is best-effort
                logger.debug("Outgoing webhook attempt logger failed: %s", e)

        last_status: Optional[int] = None
        for attempt in range(1, max_retries + 1):
            started = time.monotonic()
            try:
                async with (self._client or httpx.AsyncClient()) as client:
                    resp = await client.post(
                        request.url, content=body, headers=headers, timeout=request.timeout
                    )
                last_status = resp.status_code
                if 200 <= resp.status_code < 300:
                    await note(attempt, started, True, resp.status_code, "ok", False)
                    return WebhookResult(
                        True, resp.status_code, attempt, idem_key, signature, "ok"
                    )
                detail = f"HTTP {resp.status_code}: {resp.text[:200]}"
                if self.is_retryable_status(resp.status_code) and attempt < max_retries:
                    await note(attempt, started, False, resp.status_code, detail, True)
                    await asyncio.sleep(self._backoff_delay(attempt))
                    continue
                # Non-retryable status, or a retryable status on the final attempt.
                await note(attempt, started, False, resp.status_code, detail, False)
                return WebhookResult(False, resp.status_code, attempt, idem_key, signature, detail)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                # Transient network-level failures: retry until attempts are spent.
                detail = f"{type(e).__name__}: {e}"
                if attempt < max_retries:
                    await note(attempt, started, False, None, detail, True)
                    await asyncio.sleep(self._backoff_delay(attempt))
                    continue
                await note(attempt, started, False, None, detail, False)
                return WebhookResult(False, None, attempt, idem_key, signature, detail)
            except Exception as e:  # never raise to the caller; log + report failure
                logger.error("Outgoing webhook delivery failed: %s", e)
                detail = f"{type(e).__name__}: {e}"
                await note(attempt, started, False, None, detail, False)
                return WebhookResult(False, None, attempt, idem_key, signature, detail)

        # Exhausted all retries (defensive; the loop always returns).
        return WebhookResult(
            False, last_status, max_retries, idem_key, signature, "retries exhausted"
        )
