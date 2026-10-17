"""
Regression tests for refresh-token rotation (feature gap #1b).

Access tokens are stateless JWTs; refresh tokens are opaque, bcrypt-hashed,
DB-backed records (like APIToken) carrying a deterministic HMAC index. Each
successful rotation issues a successor that links back via
``previous_token_index``; every token is single-use, so replaying a token is
detected as a leak and revokes the whole chain (RFC 8693 style).
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from app.models.auth import User, RefreshToken
from app.services.auth_service import auth_service, pwd_context, refresh_token_index
from app.api.auth import (
    RefreshTokenRequest,
    login,
    refresh,
    logout_refresh,
    logout_all,
    get_current_user,
)


async def _make_user(db, role="user", password="strongpassword123"):
    import uuid
    user = User(username=f"rf_{role}_{uuid.uuid4().hex[:10]}", email=f"{role}@rf.test",
                password_hash=pwd_context.hash(password),
                role=role, is_active=True)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _access_token_for(db, user):
    return auth_service.create_access_token(
        data={"sub": str(user.id), "role": user.role, "username": user.username}
    )


# --- service-level behaviour ------------------------------------------------

def test_refresh_token_index_is_deterministic_hex():
    a = refresh_token_index("same")
    b = refresh_token_index("same")
    c = refresh_token_index("different")
    assert a == b
    assert a != c
    assert len(a) == 64
    assert all(ch in "0123456789abcdef" for ch in a)


@pytest.mark.asyncio
async def test_issue_refresh_token_stores_hash_not_plaintext(db_session):
    user = await _make_user(db_session)
    raw = await auth_service.issue_refresh_token(db_session, user.id)

    row = await auth_service._get_refresh_by_index(db_session, raw)
    assert row is not None
    assert row.user_id == user.id
    assert row.is_active is True
    assert row.previous_token_index is None
    # Plaintext is never persisted; only the bcrypt hash is.
    assert raw != row.token_hash
    assert pwd_context.verify(raw, row.token_hash)


@pytest.mark.asyncio
async def test_rotate_happy_path_issues_working_pair(db_session):
    user = await _make_user(db_session)
    raw = await auth_service.issue_refresh_token(db_session, user.id)

    result = await auth_service.rotate_refresh_token(db_session, raw)
    assert result is not None
    assert "access_token" in result and "refresh_token" in result
    assert result["user"]["id"] == user.id

    # The new access token authenticates the same user.
    resolved = await get_current_user(result["access_token"], db_session)
    assert resolved.id == user.id

    # The new refresh token can itself be rotated (chain continues).
    result2 = await auth_service.rotate_refresh_token(db_session, result["refresh_token"])
    assert result2 is not None


@pytest.mark.asyncio
async def test_rotate_replayed_token_revokes_entire_chain(db_session):
    """Presenting a token that was already rotated away is a leak: the whole
    chain for the user is revoked and None is returned."""
    user = await _make_user(db_session)
    raw = await auth_service.issue_refresh_token(db_session, user.id)

    first = await auth_service.rotate_refresh_token(db_session, raw)
    assert first is not None

    second = await auth_service.rotate_refresh_token(db_session, raw)
    assert second is None

    active = await auth_service.list_active_refresh_tokens(db_session, user.id)
    assert active == []


@pytest.mark.asyncio
async def test_rotate_unknown_token_returns_none(db_session):
    await _make_user(db_session)
    assert await auth_service.rotate_refresh_token(db_session, "does-not-exist") is None
    assert await auth_service.rotate_refresh_token(db_session, None) is None


@pytest.mark.asyncio
async def test_rotate_expired_token_returns_none(db_session):
    from app.services.auth_service import _utcnow

    user = await _make_user(db_session)
    raw = await auth_service.issue_refresh_token(db_session, user.id)

    row = await auth_service._get_refresh_by_index(db_session, raw)
    # timestamptz columns round-trip as tz-aware; expire using an aware "now".
    row.expires_at = _utcnow() - timedelta(days=1)
    await db_session.commit()

    assert await auth_service.rotate_refresh_token(db_session, raw) is None


@pytest.mark.asyncio
async def test_rotate_revoked_token_returns_none(db_session):
    user = await _make_user(db_session)
    raw = await auth_service.issue_refresh_token(db_session, user.id)
    assert await auth_service.revoke_single_refresh_token(db_session, raw) is True
    assert await auth_service.rotate_refresh_token(db_session, raw) is None


@pytest.mark.asyncio
async def test_rotate_hash_mismatch_returns_none(db_session):
    """A token whose index matches but whose plaintext does not verify against
    the stored bcrypt hash must be rejected."""
    user = await _make_user(db_session)
    raw = "known-raw-token"

    db_session.add(RefreshToken(
        user_id=user.id,
        token_index=refresh_token_index(raw),
        token_hash=pwd_context.hash("attacker-wrong-secret"),
        previous_token_index=None,
        expires_at=datetime.utcnow() + timedelta(days=1),
        is_active=True,
    ))
    await db_session.commit()

    assert await auth_service.rotate_refresh_token(db_session, raw) is None


@pytest.mark.asyncio
async def test_revoke_single_is_idempotent(db_session):
    user = await _make_user(db_session)
    raw = await auth_service.issue_refresh_token(db_session, user.id)
    assert await auth_service.revoke_single_refresh_token(db_session, raw) is True
    assert await auth_service.revoke_single_refresh_token(db_session, raw) is False


@pytest.mark.asyncio
async def test_revoke_all_revokes_every_token(db_session):
    user = await _make_user(db_session)
    [await auth_service.issue_refresh_token(db_session, user.id) for _ in range(3)]

    active = await auth_service.list_active_refresh_tokens(db_session, user.id)
    assert len(active) == 3

    count = await auth_service.revoke_all_user_refresh_tokens(db_session, user.id)
    assert count == 3
    assert await auth_service.list_active_refresh_tokens(db_session, user.id) == []


@pytest.mark.asyncio
async def test_list_active_excludes_expired_and_inactive(db_session):
    user = await _make_user(db_session)
    fresh = await auth_service.issue_refresh_token(db_session, user.id)

    stale = await auth_service.issue_refresh_token(db_session, user.id)
    row = await auth_service._get_refresh_by_index(db_session, stale)
    row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()

    active = await auth_service.list_active_refresh_tokens(db_session, user.id)
    fresh_row = await auth_service._get_refresh_by_index(db_session, fresh)
    stale_row = await auth_service._get_refresh_by_index(db_session, stale)
    assert fresh_row.id in {s["id"] for s in active}
    assert stale_row.id not in {s["id"] for s in active}


@pytest.mark.asyncio
async def test_sessions_listing_excludes_rotated_away_parent(db_session):
    """A parent that has been rotated away stays is_active (so its replay is
    detectable as a leak) but must not be listed as a usable session."""
    user = await _make_user(db_session)
    parent = await auth_service.issue_refresh_token(db_session, user.id)
    result = await auth_service.rotate_refresh_token(db_session, parent)
    assert result is not None

    live_ids = {s["id"] for s in await auth_service.list_active_refresh_tokens(db_session, user.id)}
    parent_row = await auth_service._get_refresh_by_index(db_session, parent)
    successor_row = await auth_service._get_refresh_by_index(db_session, result["refresh_token"])
    assert parent_row.id not in live_ids      # rotated away -> not a usable session
    assert successor_row.id in live_ids        # current tip -> listed


# --- endpoint-level regression guards ---------------------------------------

@pytest.mark.asyncio
async def test_login_returns_usable_refresh_token(db_session):
    user = await _make_user(db_session)
    form = OAuth2PasswordRequestForm(username=user.username, password="strongpassword123")
    resp = await login(form, db_session)
    assert resp.get("refresh_token")
    result = await auth_service.rotate_refresh_token(db_session, resp["refresh_token"])
    assert result is not None


@pytest.mark.asyncio
async def test_refresh_endpoint_invalid_returns_401(db_session):
    with pytest.raises(HTTPException) as exc:
        await refresh(RefreshTokenRequest(refresh_token="bogus"), db_session)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_endpoint_rotates_valid_token(db_session):
    user = await _make_user(db_session)
    raw = await auth_service.issue_refresh_token(db_session, user.id)
    resp = await refresh(RefreshTokenRequest(refresh_token=raw), db_session)
    assert resp["access_token"] and resp["refresh_token"]


@pytest.mark.asyncio
async def test_logout_refresh_revokes_token(db_session):
    user = await _make_user(db_session)
    raw = await auth_service.issue_refresh_token(db_session, user.id)
    r = await logout_refresh(RefreshTokenRequest(refresh_token=raw), db_session)
    assert r["success"] is True
    assert await auth_service.rotate_refresh_token(db_session, raw) is None


@pytest.mark.asyncio
async def test_logout_all_endpoint(db_session):
    """logout_all is guarded by get_current_user; a valid token revokes every
    refresh token for that user."""
    user = await _make_user(db_session)
    good = await _access_token_for(db_session, user)
    await auth_service.issue_refresh_token(db_session, user.id)
    await auth_service.issue_refresh_token(db_session, user.id)

    resolved = await get_current_user(good, db_session)
    r = await logout_all(resolved, db_session)
    assert r["success"] is True
    # Every token for the user is now revoked.
    assert await auth_service.list_active_refresh_tokens(db_session, user.id) == []


@pytest.mark.asyncio
async def test_auth_guard_refuses_bad_token(db_session):
    """The dependency logout_all relies on refuses an invalid/revoked access
    token with 401 (so logout-all can never be called unauthenticated)."""
    with pytest.raises(HTTPException) as exc:
        await get_current_user("not-a-real-token", db_session)
    assert exc.value.status_code == 401


def test_refresh_request_model():
    body = RefreshTokenRequest(refresh_token="abc")
    assert body.refresh_token == "abc"
