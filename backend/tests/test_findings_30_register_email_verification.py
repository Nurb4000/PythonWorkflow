"""
Regression tests for findings #30 (/auth/register open -> unverified accounts).

Self-registration was open to anonymous callers: anyone could obtain a valid JWT
+ refresh token pair with no email proof. The fix (findings #30):
  * register creates an *unverified* account and emails a short-lived verification
    token (best-effort — registration still succeeds if SMTP is unavailable);
  * get_current_user rejects unverified users with HTTP 403;
  * POST /auth/verify-email validates the token and sets is_verified=True.

These tests exercise the real register/verify_email/get_current_user code paths
with a fake db + monkeypatched auth_service methods (no live PostgreSQL needed).
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.api.auth import register, verify_email, get_current_user
from app.services.auth_service import auth_service


class FakeUser:
    def __init__(self, uid=1, is_verified=False, is_active=True):
        self.id = uid
        self.username = "alice"
        self.email = "alice@example.com"
        self.role = "user"
        self.is_verified = is_verified
        self.is_active = is_active


class FakeRequest:
    def __init__(self, data=None, url_root="http://testserver"):
        self._data = data or {}
        self.url_root = url_root

    async def json(self):
        return self._data


class FakeDB:
    async def execute(self, stmt):
        class R:
            def scalar_one_or_none(r):
                return None
        return R()

    async def commit(self):
        pass


# --- register creates an unverified account and emails a verification token -----

async def test_register_creates_unverified_account(monkeypatch):
    sent = {}
    create_kwargs = {}

    async def fake_create_user(db=None, **kwargs):
        create_kwargs.update(kwargs)
        return FakeUser(uid=1, is_verified=False)

    def fake_send_email(to, subject, body, **kw):
        sent.update(to=to, body=body)
        return {"sent": True}

    monkeypatch.setattr(auth_service, "create_user", fake_create_user)
    monkeypatch.setattr("app.services.email_service.send_email", fake_send_email)

    result = await register(
        FakeRequest({"full_name": "Alice"}),
        "alice", "alice@example.com", "password123",
        db=FakeDB(),
    )

    # register must ask create_user to make the account unverified...
    assert create_kwargs.get("is_verified") is False
    # ...and surface that state to the caller.
    assert result["user"]["is_verified"] is False
    assert "verify" in result["message"].lower()
    # A verification email was sent to the registered address, with a verify link.
    assert sent["to"] == "alice@example.com"
    assert "verify-email" in sent["body"]


class _NoRowResult:
    def scalar_one_or_none(self):
        return None


class _CreateDB:
    """Fake db for create_user: no existing user, no duplicate email."""

    def __init__(self):
        self.added = []

    async def execute(self, stmt):
        return _NoRowResult()

    def add(self, user):
        self.added.append(user)

    async def commit(self):
        pass

    async def refresh(self, user):
        pass


async def test_create_user_honors_is_verified_flag():
    # is_verified=False -> unverified account (self-registration path).
    unverified = await auth_service.create_user(
        _CreateDB(), "uuser", "u@example.com", "pass", is_verified=False
    )
    assert unverified.is_verified is False
    # Default remains True so admin/trusted-created users are not locked out.
    default_user = await auth_service.create_user(
        _CreateDB(), "duser", "d@example.com", "pass"
    )
    assert default_user.is_verified is True


async def test_register_succeeds_even_if_email_fails(monkeypatch):
    async def fake_create_user(db=None, **kwargs):
        return FakeUser(uid=1, is_verified=False)

    def boom(to, subject, body, **kw):
        raise RuntimeError("SMTP down")

    monkeypatch.setattr(auth_service, "create_user", fake_create_user)
    monkeypatch.setattr("app.services.email_service.send_email", boom)

    # Registration must still succeed (best-effort email).
    result = await register(
        FakeRequest(), "alice", "alice@example.com", "password123", db=FakeDB()
    )
    assert result["user"]["is_verified"] is False


# --- verify-email endpoint -----------------------------------------------------

async def test_verify_email_sets_is_verified(monkeypatch):
    token = auth_service.create_verification_token(1)
    user = FakeUser(uid=1, is_verified=False)

    async def fake_get_user_by_id(db, uid):
        return user

    monkeypatch.setattr(auth_service, "get_user_by_id", fake_get_user_by_id)

    result = await verify_email(token=token, db=FakeDB())

    assert result["message"] == "Email verified successfully"
    assert user.is_verified is True


async def test_verify_email_rejects_invalid_token():
    with pytest.raises(HTTPException) as exc:
        await verify_email(token="not.a.real.token", db=FakeDB())
    assert exc.value.status_code == 400


async def test_verify_email_rejects_wrong_type_token(monkeypatch):
    # A normal access token (no type=email_verification) must not verify email.
    token = auth_service.create_access_token({"sub": "1"})

    async def fake_get_user_by_id(db, uid):
        return FakeUser(uid=1, is_verified=False)

    monkeypatch.setattr(auth_service, "get_user_by_id", fake_get_user_by_id)

    with pytest.raises(HTTPException) as exc:
        await verify_email(token=token, db=FakeDB())
    assert exc.value.status_code == 400


# --- get_current_user gates on is_verified -------------------------------------

def _valid_payload():
    now = datetime.now(timezone.utc)
    return {
        "sub": "1",
        "exp": now + timedelta(hours=1),
        "iat": now,
        "jti": "abc",
    }


async def test_get_current_user_rejects_unverified(monkeypatch):
    async def fake_verify_token(db, token):
        return _valid_payload()

    async def fake_get_user_by_id(db, uid):
        return FakeUser(uid=1, is_verified=False)

    monkeypatch.setattr(auth_service, "verify_token", fake_verify_token)
    monkeypatch.setattr(auth_service, "get_user_by_id", fake_get_user_by_id)

    with pytest.raises(HTTPException) as exc:
        await get_current_user(token="x", db=FakeDB())
    assert exc.value.status_code == 403
    assert "verified" in exc.value.detail.lower()


async def test_get_current_user_allows_verified(monkeypatch):
    async def fake_verify_token(db, token):
        return _valid_payload()

    async def fake_get_user_by_id(db, uid):
        return FakeUser(uid=1, is_verified=True)

    monkeypatch.setattr(auth_service, "verify_token", fake_verify_token)
    monkeypatch.setattr(auth_service, "get_user_by_id", fake_get_user_by_id)

    user = await get_current_user(token="x", db=FakeDB())
    assert user.is_verified is True
