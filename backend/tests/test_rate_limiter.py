"""
Regression tests for M5: broad API rate limiting.

Covers three things:
  * the shared sliding-window limiter (``app.services.rate_limiter.RateLimiter``) --
    allow/over-limit, per-key isolation, window eviction, reset;
  * the ``require_api_rate_limit`` FastAPI dependency that maps an over-limit client
    IP to HTTP 429 with a ``Retry-After`` header (tested both against a fake Request
    and through real FastAPI routing with a real TestClient request); and
  * the wiring of that dependency onto the high-cost / high-touch routers
    (/ai/*, /data-query/*, /data-export/*) in ``app.main``.

The limits are read from ``settings`` on every call, so tests raise/lower them via
``object.__setattr__`` (pydantic-settings ignores plain assignment), exactly like
``test_ai_usage_throttle.py``.
"""
import time
import types

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

import app.core.config as config_mod
from app.core.config import settings
from app.services.rate_limiter import (
    RateLimitError,
    api_rate_limiter,
    require_api_rate_limit,
)


@pytest.fixture(autouse=True)
def _isolated_limiter():
    """Give each test a fresh limiter and restore settings afterwards."""
    saved_window = settings.api_request_window_seconds
    saved_max = settings.api_requests_per_window
    api_rate_limiter.reset_all()
    yield
    api_rate_limiter.reset_all()
    object.__setattr__(settings, "api_request_window_seconds", saved_window)
    object.__setattr__(settings, "api_requests_per_window", saved_max)


def _limit(n):
    object.__setattr__(settings, "api_requests_per_window", n)


def _window(sec):
    object.__setattr__(settings, "api_request_window_seconds", sec)


def _request(ip="203.0.113.7"):
    """Fake Request exposing only what ``require_api_rate_limit`` reads."""
    return types.SimpleNamespace(client=types.SimpleNamespace(host=ip))


# --- RateLimiter unit behaviour -----------------------------------------------

def test_under_limit_allows():
    _limit(3)
    assert api_rate_limiter.allow("a") is True
    assert api_rate_limiter.allow("a") is True
    assert api_rate_limiter.allow("a") is True


def test_over_limit_rejects_and_does_not_record():
    _limit(2)
    assert api_rate_limiter.allow("a") is True
    assert api_rate_limiter.allow("a") is True
    # Third request in the same window is over quota.
    assert api_rate_limiter.allow("a") is False
    # Rejected requests are not counted, so remaining reflects only accepted ones.
    assert api_rate_limiter.remaining("a") == 0


def test_enforce_raises_over_limit():
    _limit(1)
    api_rate_limiter.enforce("k")  # first allowed, no raise
    with pytest.raises(RateLimitError):
        api_rate_limiter.enforce("k")


def test_keys_are_isolated():
    _limit(1)
    assert api_rate_limiter.allow("user:1") is True
    assert api_rate_limiter.allow("user:1") is False
    # A different key is unaffected.
    assert api_rate_limiter.allow("user:2") is True


def test_window_eviction_allows_retry_after_sleep():
    _limit(2)
    _window(0.3)  # short rolling window so eviction is testable
    assert api_rate_limiter.allow("k") is True
    assert api_rate_limiter.allow("k") is True
    assert api_rate_limiter.allow("k") is False
    # After the (short) window slides, old entries are pruned and usage resumes.
    time.sleep(0.4)
    assert api_rate_limiter.allow("k") is True


def test_reset_clears_counter():
    _limit(1)
    assert api_rate_limiter.allow("k") is True
    assert api_rate_limiter.allow("k") is False
    api_rate_limiter.reset("k")
    assert api_rate_limiter.allow("k") is True


# --- require_api_rate_limit dependency ----------------------------------------

def test_dependency_allows_under_limit():
    _limit(2)
    # No exception raised while under the limit.
    require_api_rate_limit(_request("198.51.100.1"))
    require_api_rate_limit(_request("198.51.100.1"))


def test_dependency_raises_429_when_over_limit():
    from fastapi import HTTPException

    _limit(1)
    require_api_rate_limit(_request("198.51.100.9"))  # first allowed, no raise
    with pytest.raises(HTTPException) as exc:
        require_api_rate_limit(_request("198.51.100.9"))
    assert exc.value.status_code == 429
    assert exc.value.headers.get("Retry-After") == "60"


def test_dependency_keys_per_ip():
    from fastapi import HTTPException

    _limit(1)
    require_api_rate_limit(_request("198.51.100.1"))
    # A different source IP is unaffected.
    require_api_rate_limit(_request("198.51.100.2"))
    with pytest.raises(HTTPException):
        require_api_rate_limit(_request("198.51.100.1"))  # same IP, now over limit


def test_dependency_real_routing_returns_429():
    """End-to-end through real FastAPI routing + a real TestClient request.

    Proves the dependency is honored by the routing layer (not just when called
    directly) and that it maps over-limit to 429 with a Retry-After header.
    """
    _limit(2)
    _window(60)

    router = APIRouter(dependencies=[Depends(require_api_rate_limit)])

    @router.get("/ping")
    def ping():
        return {"ok": True}

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    resp = client.get("/ping")
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "60"


# --- wiring onto the real routers in app.main ---------------------------------
#
# The high-cost / high-touch routers are wired with the same
# ``dependencies=[Depends(require_api_rate_limit)]`` in app.main. Rather than
# inspect FastAPI internals, we prove it end-to-end: drive the real app through
# TestClient with auth overridden, and confirm the per-IP guard returns 429 (with
# Retry-After) once the client IP exceeds the cap.

def _override_auth(app):
    """Bypass get_current_developer/get_current_user/get_db so we reach the guard."""
    from app.api.auth import get_current_developer, get_current_user
    from app.core.database import get_db

    class FakeUser:
        id = 1
        role = "developer"

    app.dependency_overrides[get_current_developer] = lambda: FakeUser()
    app.dependency_overrides[get_current_user] = lambda: FakeUser()

    async def fake_get_db():
        yield object()

    app.dependency_overrides[get_db] = fake_get_db


def test_real_app_enforces_rate_limit_on_export():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.rate_limiter import api_rate_limiter

    _override_auth(app)
    _limit(2)
    api_rate_limiter.reset_all()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        # Under the limit the guard passes (the endpoint then 500s on the fake db,
        # but crucially it is NOT rate-limited).
        assert client.get("/data-export/table/users?limit=10").status_code != 429
        assert client.get("/data-export/table/users?limit=10").status_code != 429
        # The third request from the same IP is over the cap -> 429 + Retry-After.
        resp = client.get("/data-export/table/users?limit=10")
        assert resp.status_code == 429
        assert resp.headers["Retry-After"] == "60"
    finally:
        app.dependency_overrides.clear()
        api_rate_limiter.reset_all()


def test_real_app_enforces_rate_limit_on_query():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.rate_limiter import api_rate_limiter

    _override_auth(app)
    _limit(1)
    api_rate_limiter.reset_all()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        assert client.post("/data-query/sql", json={"sql": "SELECT 1"}).status_code != 429
        resp = client.post("/data-query/sql", json={"sql": "SELECT 1"})
        assert resp.status_code == 429
        assert resp.headers["Retry-After"] == "60"
    finally:
        app.dependency_overrides.clear()
        api_rate_limiter.reset_all()
