"""
M5 fix: shared API rate limiter (per-IP sliding window).

Login brute-force protection (``app.api.auth``) already bounds ``POST /auth/login``
and a per-user AI cost throttle (``app.services.ai_usage_service``) caps paid LLM
calls per account. But the high-cost / high-touch endpoints -- ``/ai/*``,
``/data-query/*`` and ``/data-export/*`` -- had *no* request-frequency limit at
all, so a single source could flood them (DoS) or, for AI, rack up unbounded LLM
cost across many accounts.

This module provides one small, in-memory sliding-window limiter keyed by an
arbitrary string (here: the client's transport socket IP) plus a FastAPI
dependency (``require_api_rate_limit``) that enforces a per-IP cap on those
endpoints and maps an over-limit result to HTTP 429 with a ``Retry-After`` header.

Design notes:
* The limiter mirrors the existing sliding-window style used by the login guard
  and the webhook limiter (monotonic timestamps, prune-then-count) but is factored
  into a reusable, dependency-free class so every endpoint shares one implementation
  instead of a fresh copy of the bookkeeping.
* Limits are read from ``settings`` on every call (like ``ai_usage_service``) so
  operators can tune them via env vars without restarting, and tests can raise or
  lower them.
* The hot path (``RateLimiter``) has no FastAPI dependency, so it is unit-testable
  without the API layer; only ``require_api_rate_limit`` translates the result into
  an HTTP response.
"""
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import HTTPException, Request

from app.core.config import settings


class RateLimitError(Exception):
    """Raised internally when a key exceeds its window quota (maps to HTTP 429)."""

    def __init__(self, window_seconds: float):
        self.window_seconds = int(window_seconds)
        super().__init__("API rate limit exceeded")


class RateLimiter:
    """Thread-safe-enough in-memory sliding-window counter.

    asyncio runs single-threaded and every FastAPI handler is a coroutine on that
    event loop, so the synchronous read-modify-write here is safe across requests
    (same guarantee as the login / webhook limiters).
    """

    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)

    @property
    def max_requests(self) -> int:
        return int(getattr(settings, "api_requests_per_window", 60))

    @property
    def window_seconds(self) -> float:
        # Keep as float so short windows (e.g. in tests) are not truncated to 0.
        return float(getattr(settings, "api_request_window_seconds", 60))

    def _prune(self, key: str, now: float) -> None:
        dq = self._requests[key]
        cutoff = now - self.window_seconds
        while dq and dq[0] < cutoff:
            dq.popleft()

    def allow(self, key: str) -> bool:
        """Record a request for *key*; return True if allowed, False if over quota.

        Does not record when over limit so the window recovers naturally.
        """
        now = time.monotonic()
        self._prune(key, now)
        dq = self._requests[key]
        if len(dq) >= self.max_requests:
            return False
        dq.append(now)
        return True

    def enforce(self, key: str) -> None:
        """Consume a slot for *key* or raise :class:`RateLimitError`.

        The single decision point used by the FastAPI dependency; keeping it here
        (rather than in an endpoint) makes the throttle unit-testable without
        importing the API layer.
        """
        if not self.allow(key):
            raise RateLimitError(self.window_seconds)

    def remaining(self, key: str) -> int:
        now = time.monotonic()
        self._prune(key, now)
        return max(0, self.max_requests - len(self._requests[key]))

    def reset(self, key: str) -> None:
        self._requests.pop(key, None)

    def reset_all(self) -> None:
        self._requests.clear()


# Shared limiter instance for the general API / data / AI request-frequency cap.
api_rate_limiter = RateLimiter()


def _client_ip(request: Optional[Request]) -> str:
    """Return the client's transport socket IP (not the spoofable X-Forwarded-For).

    Same choice as the webhook rate limiter (``app.api.webhooks``): keying on
    ``request.client.host`` means a proxy in front cannot spread one attacker
    across many forged source IPs. ``None`` is allowed for direct coroutine calls
    in tests and for internal callers without an HTTP request.
    """
    client = getattr(request, "client", None)
    if client is not None and getattr(client, "host", None):
        return client.host
    return "unknown"


def require_api_rate_limit(request: Request) -> None:
    """FastAPI dependency: reject with HTTP 429 when the client IP is over quota.

    Apply it to a router with ``APIRouter(dependencies=[Depends(require_api_rate_limit)])``
    or ``app.include_router(r, dependencies=[Depends(require_api_rate_limit)])`` so
    every route in that router shares the per-IP cap. Cheap and auth-independent, so
    it bounds request frequency before any heavier dependency (DB lookups, model
    calls) runs.
    """
    key = f"api:{_client_ip(request)}"
    try:
        api_rate_limiter.enforce(key)
    except RateLimitError as e:
        remaining = int(api_rate_limiter.remaining(key))
        raise HTTPException(
            status_code=429,
            detail=(
                "API rate limit exceeded. Try again in ~{}s ({} requests "
                "remaining in the next window)."
            ).format(e.window_seconds, remaining),
            headers={"Retry-After": str(e.window_seconds)},
        )


async def require_export_rate_limit(request: Request) -> None:
    """Export-router variant of :func:`require_api_rate_limit` (G7).

    Same per-IP sliding-window guard and 429 response, but an over-limit event on
    a /data-export path also emits a best-effort admin alert. Kept separate so
    /ai/* and /data-query/* throttling stays silent; making the shared dependency
    async would also break its existing synchronous callers.
    """
    key = f"api:{_client_ip(request)}"
    try:
        api_rate_limiter.enforce(key)
    except RateLimitError as e:
        # Lazy import avoids pulling notification services into the hot path of
        # every request and keeps the RateLimiter unit-testable in isolation.
        from app.services.export_alert_service import alert_export_rate_limited

        url = getattr(request, "url", None)
        try:
            await alert_export_rate_limited(
                client_ip=_client_ip(request),
                path=getattr(url, "path", None) or "/data-export",
                retry_after=e.window_seconds,
                limit=api_rate_limiter.max_requests,
                window_seconds=e.window_seconds,
            )
        except Exception:
            # Alerting is best-effort; a notification failure must never turn
            # the 429 into a 500 or swallow the Retry-After header.
            pass
        remaining = int(api_rate_limiter.remaining(key))
        raise HTTPException(
            status_code=429,
            detail=(
                "API rate limit exceeded. Try again in ~{}s ({} requests "
                "remaining in the next window)."
            ).format(e.window_seconds, remaining),
            headers={"Retry-After": str(e.window_seconds)},
        )
