"""
M7 fix: per-user AI usage throttle.

Paid LLM calls (OpenAI, or a remote llama.cpp server) cost money per request.
Before this fix any authenticated user could chain an unbounded number of
``generate_*``/``assist_*`` calls and rack up the bill.

This module implements a simple rolling-window counter keyed by user id. The
``require_ai_quota`` dependency in ``app.api.ai`` calls ``consume()`` once per
request; when a user exceeds ``ai_requests_per_window`` inside the
``ai_request_window_seconds`` window the request is rejected with HTTP 429.

The limits are read from ``settings`` on every call so operators can tune them
via environment variables without restarting, and tests can raise/lower them.
"""
import time
from collections import defaultdict, deque

from app.core.config import settings


class AIUsageLimitError(Exception):
    """Raised internally when a user is over their AI quota."""

    def __init__(self, window_seconds: int):
        self.window_seconds = window_seconds
        super().__init__("AI usage limit exceeded")


class AIUsageLimiter:
    def __init__(self) -> None:
        self._requests: dict[int, deque[float]] = defaultdict(deque)

    @property
    def max_requests(self) -> int:
        return int(getattr(settings, "ai_requests_per_window", 100))

    @property
    def window_seconds(self) -> float:
        # Keep as float so short windows (e.g. tests) are not truncated to 0.
        return float(getattr(settings, "ai_request_window_seconds", 3600))

    def _prune(self, key: int, now: float) -> None:
        dq = self._requests[key]
        cutoff = now - self.window_seconds
        while dq and dq[0] < cutoff:
            dq.popleft()

    def consume(self, key: int) -> bool:
        """Record a request for *key*.

        Returns True if the request is allowed, False if the user is over their
        quota for the current window. Does not record when over limit so the
        window can recover naturally.
        """
        now = time.monotonic()
        self._prune(key, now)
        dq = self._requests[key]
        if len(dq) >= self.max_requests:
            return False
        dq.append(now)
        return True

    def enforce(self, key: int) -> None:
        """Consume a slot for *key* or raise :class:`AIUsageLimitError`.

        This is the single decision point used by the FastAPI dependency; keeping
        it here (rather than in the endpoint) makes the throttle unit-testable
        without importing the API module.
        """
        if not self.consume(key):
            raise AIUsageLimitError(self.window_seconds)

    def remaining(self, key: int) -> int:
        now = time.monotonic()
        self._prune(key, now)
        return max(0, self.max_requests - len(self._requests[key]))

    def reset(self, key: int) -> None:
        self._requests.pop(key, None)

    def reset_all(self) -> None:
        self._requests.clear()


ai_usage = AIUsageLimiter()
