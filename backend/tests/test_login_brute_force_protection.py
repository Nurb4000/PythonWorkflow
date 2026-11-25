"""
Regression tests for findings #6: /auth/login had no brute-force protection.
authenticate_user returns a uniform None on bad credentials, which stops user
enumeration but bounds nothing - an attacker can guess passwords unlimited times.
These tests pin the per-username lockout and per-IP rate-limit guards added to
auth.py (check_login_rate_limit / record_failed_login / check_ip_login_rate_limit).
"""
import types

import pytest

import app.api.auth as auth_mod


@pytest.fixture(autouse=True)
def _reset_state():
    """Isolate each test from the module-level attempt/lockout buckets."""
    auth_mod._failed_login_attempts.clear()
    auth_mod._login_lockuntil.clear()
    auth_mod._ip_login_times.clear()
    yield
    auth_mod._failed_login_attempts.clear()
    auth_mod._login_lockuntil.clear()
    auth_mod._ip_login_times.clear()


def _form(username, password):
    return types.SimpleNamespace(username=username, password=password)


def _req(ip="9.9.9.9"):
    return types.SimpleNamespace(client=types.SimpleNamespace(host=ip), headers={})


def _ok_user():
    return types.SimpleNamespace(id=7, role="user", username="carol",
                                 email="c@x.test", full_name="Carol")


# --- helper-level behaviour -------------------------------------------------

def test_no_lockout_before_threshold():
    assert auth_mod.check_login_rate_limit("alice") is False
    for _ in range(auth_mod.LOGIN_MAX_FAILURES - 1):
        auth_mod.record_failed_login("alice")
        assert auth_mod.check_login_rate_limit("alice") is False


def test_lockout_after_max_failures():
    for _ in range(auth_mod.LOGIN_MAX_FAILURES):
        auth_mod.record_failed_login("alice")
    assert auth_mod.check_login_rate_limit("alice") is True


def test_reset_login_state_clears_lockout():
    for _ in range(auth_mod.LOGIN_MAX_FAILURES):
        auth_mod.record_failed_login("alice")
    assert auth_mod.check_login_rate_limit("alice") is True
    auth_mod.reset_login_state("alice")
    assert auth_mod.check_login_rate_limit("alice") is False


def test_lockout_expires_after_window():
    fake = {"t": 1000.0}
    real = auth_mod.time.monotonic
    auth_mod.time.monotonic = lambda: fake["t"]
    try:
        for _ in range(auth_mod.LOGIN_MAX_FAILURES):
            auth_mod.record_failed_login("bob")
        assert auth_mod.check_login_rate_limit("bob") is True
        fake["t"] += auth_mod.LOGIN_WINDOW_SECONDS + auth_mod.LOGIN_LOCKOUT_SECONDS + 1
        assert auth_mod.check_login_rate_limit("bob") is False
    finally:
        auth_mod.time.monotonic = real


def test_ip_rate_limit_independent_of_username():
    assert auth_mod.check_ip_login_rate_limit("1.2.3.4") is False
    for _ in range(auth_mod.LOGIN_IP_MAX - 1):
        auth_mod.record_ip_login("1.2.3.4")
        assert auth_mod.check_ip_login_rate_limit("1.2.3.4") is False
    auth_mod.record_ip_login("1.2.3.4")
    assert auth_mod.check_ip_login_rate_limit("1.2.3.4") is True


# --- endpoint-level behaviour ----------------------------------------------

async def _login_status(form, req, db):
    """Call the login coroutine and return its HTTP status code.

    FastAPI normally converts HTTPException into a response; calling the coroutine
    directly re-raises it, so translate it back to a status code here.
    """
    from fastapi import HTTPException
    from app.api.auth import login
    try:
        resp = await login(form, req, db)
    except HTTPException as e:
        return e.status_code
    # Direct coroutine calls return the raw body (a dict); FastAPI would wrap it in a
    # 200 Response. Default to 200 when there is no status_code attribute.
    return getattr(resp, "status_code", 200)


@pytest.mark.asyncio
async def test_login_endpoint_locks_out_after_repeated_failures(monkeypatch):
    from app.api.auth import login

    async def fake_authenticate(db, username, password):
        return None  # always fail

    monkeypatch.setattr(auth_mod.auth_service, "authenticate_user", fake_authenticate)

    # First LOGIN_MAX_FAILURES attempts record failures and return 401; the next is
    # locked out with 429.
    for _ in range(auth_mod.LOGIN_MAX_FAILURES):
        resp = await _login_status(_form("carol", "bad"), _req(), None)
        assert resp == 401

    resp = await _login_status(_form("carol", "bad"), _req(), None)
    assert resp == 429


@pytest.mark.asyncio
async def test_login_success_resets_failure_state(monkeypatch):
    from app.api.auth import login

    # Pre-load a few (below threshold) failures so the account is not yet locked.
    for _ in range(2):
        auth_mod.record_failed_login("carol")

    async def fake_authenticate(db, username, password):
        return _ok_user()

    async def fake_issue_refresh(db, user_id):
        return "rt"

    monkeypatch.setattr(auth_mod.auth_service, "authenticate_user", fake_authenticate)
    monkeypatch.setattr(auth_mod.auth_service, "issue_refresh_token", fake_issue_refresh)

    class _FakeDB(dict):
        async def commit(self):
            pass

    resp = await _login_status(_form("carol", "good"), _req(), _FakeDB())
    assert resp == 200
    # Success cleared the accumulated failures.
    assert auth_mod._failed_login_attempts.get("carol", []) == []
    assert auth_mod.check_login_rate_limit("carol") is False


@pytest.mark.asyncio
async def test_login_endpoint_ip_rate_limit(monkeypatch):
    from app.api.auth import login

    monkeypatch.setattr(auth_mod, "LOGIN_IP_MAX", 3)

    async def fake_authenticate(db, username, password):
        return None

    monkeypatch.setattr(auth_mod.auth_service, "authenticate_user", fake_authenticate)

    # With a per-IP cap of 3, the 4th attempt from the same IP is rate limited (429),
    # even though the username has < LOGIN_MAX_FAILURES failures.
    for _ in range(3):
        resp = await _login_status(_form("dave", "bad"), _req("5.5.5.5"), None)
        assert resp == 401

    resp = await _login_status(_form("dave", "bad"), _req("5.5.5.5"), None)
    assert resp == 429
