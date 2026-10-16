"""
Regression tests for M7: per-user AI usage throttle.

Covers the rolling-window limiter, the enforce() decision point used by the
``require_ai_quota`` FastAPI dependency, and window eviction so a user recovers
after the window slides. The paid-LLM endpoints in ``app.api.ai`` call
``ai_usage.enforce(user.id)`` before any request reaches the model; if it is
over quota an ``AIUsageLimitError`` is raised and mapped to HTTP 429.
"""
import time

import pytest

from app.core.config import settings
from app.services.ai_usage_service import AIUsageLimiter, AIUsageLimitError, ai_usage


@pytest.fixture(autouse=True)
def _isolated_limiter():
    """Give each test a fresh limiter and restore settings afterwards."""
    saved_window = settings.ai_request_window_seconds
    saved_max = settings.ai_requests_per_window
    ai_usage.reset_all()
    yield
    ai_usage.reset_all()
    object.__setattr__(settings, "ai_request_window_seconds", saved_window)
    object.__setattr__(settings, "ai_requests_per_window", saved_max)


def _limit(n: int):
    """Force the per-window request cap (pydantic settings ignore plain assignment)."""
    object.__setattr__(settings, "ai_requests_per_window", n)


def _window(sec: float):
    """Force a custom rolling-window length in seconds."""
    object.__setattr__(settings, "ai_request_window_seconds", sec)


def _user(uid: int = 1):
    """Stub principal matching what require_ai_quota reads."""
    return type("U", (), {"id": uid})()


def test_within_limit_allows():
    _limit(3)
    assert ai_usage.consume(1) is True
    assert ai_usage.consume(1) is True
    assert ai_usage.consume(1) is True
    # Fourth request in the same window is over quota.
    assert ai_usage.consume(1) is False
    assert ai_usage.remaining(1) == 0


def test_per_user_isolation():
    _limit(1)
    assert ai_usage.consume(1) is True
    assert ai_usage.consume(1) is False  # user 1 exhausted
    assert ai_usage.consume(2) is True  # user 2 unaffected


def test_enforce_raises_when_over_limit():
    _limit(1)
    ai_usage.enforce(7)  # first allowed, no raise
    with pytest.raises(AIUsageLimitError):
        ai_usage.enforce(7)


def test_window_eviction_allows_retry_after_sleep():
    _limit(2)
    _window(0.3)  # short rolling window so eviction is testable
    assert ai_usage.consume(9) is True
    assert ai_usage.consume(9) is True
    assert ai_usage.consume(9) is False
    # After the (short) window slides, old entries are pruned and usage resumes.
    time.sleep(0.4)
    assert ai_usage.consume(9) is True


def test_reset_clears_counter():
    _limit(1)
    assert ai_usage.consume(3) is True
    assert ai_usage.consume(3) is False
    ai_usage.reset(3)
    assert ai_usage.consume(3) is True
