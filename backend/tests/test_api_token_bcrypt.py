"""
Regression tests for L2: API-token verification uses bcrypt (not unsalted SHA256).

The old ``check_api_token_cmdb_permission`` hashed the incoming token with
SHA256 and matched against ``APIToken.token_hash`` — but tokens are stored with
bcrypt, so the lookup could never match (breaking CMDB API-token auth) and used
a fast unsalted hash. These tests assert bcrypt verification + permission
enforcement now work end to end.
"""
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.api.auth import check_api_token_cmdb_permission
from app.services.auth_service import pwd_context
from app.models.auth import User, APIToken


async def _make_user(db, role="developer"):
    user = User(username=f"l2_{role}_{uuid4().hex[:8]}", email=f"{role}@l2.test",
                password_hash=pwd_context.hash("strongpassword123"),
                role=role, is_active=True)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _token_record(db, user, permissions, plaintext="super-secret-api-token"):
    api_token = APIToken(
        user_id=user.id,
        name=f"test-{permissions}",
        token_hash=pwd_context.hash(plaintext),
        permissions=permissions,
        is_active=True,
    )
    db.add(api_token)
    await db.commit()
    return plaintext


@pytest.mark.asyncio
async def test_valid_api_token_with_permission_passes(db_session):
    user = await _make_user(db_session)
    plaintext = await _token_record(db_session, user, "cmdb_read,cmdb_write")
    resolved = await check_api_token_cmdb_permission(plaintext, db_session)
    assert resolved.id == user.id


@pytest.mark.asyncio
async def test_api_token_missing_permission_is_403(db_session):
    from fastapi import HTTPException
    user = await _make_user(db_session)
    plaintext = await _token_record(db_session, user, "workflow_read")
    with pytest.raises(HTTPException) as exc:
        await check_api_token_cmdb_permission(plaintext, db_session)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_inactive_token_rejected(db_session):
    from fastapi import HTTPException
    user = await _make_user(db_session)
    api_token = APIToken(
        user_id=user.id, name="inactive",
        token_hash=pwd_context.hash("inactive-token-xyz"),
        permissions="cmdb_read", is_active=False,
    )
    db_session.add(api_token)
    await db_session.commit()
    with pytest.raises(HTTPException):
        await check_api_token_cmdb_permission("inactive-token-xyz", db_session)


@pytest.mark.asyncio
async def test_expired_token_rejected(db_session):
    from fastapi import HTTPException
    user = await _make_user(db_session)
    # Naive UTC datetime, matching how create_api_token() stores expires_at.
    api_token = APIToken(
        user_id=user.id, name="expired",
        token_hash=pwd_context.hash("expired-token-xyz"),
        permissions="cmdb_read", is_active=True,
        expires_at=datetime.utcnow() - timedelta(days=1),
    )
    db_session.add(api_token)
    await db_session.commit()
    with pytest.raises(HTTPException):
        await check_api_token_cmdb_permission("expired-token-xyz", db_session)


@pytest.mark.asyncio
async def test_aware_expiry_expired_token_rejected(db_session):
    """An APIToken whose expires_at is a tz-aware datetime (as Postgres returns a
    timestamptz column) must still be rejected as expired — not crash with a
    naive/aware TypeError in the comparison."""
    from fastapi import HTTPException
    from datetime import timezone

    user = await _make_user(db_session)
    api_token = APIToken(
        user_id=user.id, name="aware-expired",
        token_hash=pwd_context.hash("aware-expired-token"),
        permissions="cmdb_read", is_active=True,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(api_token)
    await db_session.commit()
    # Before the fix this raised TypeError (offset-naive vs offset-aware); now it
    # correctly surfaces as a 401.
    with pytest.raises(HTTPException) as exc:
        await check_api_token_cmdb_permission("aware-expired-token", db_session)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_aware_expiry_valid_token_passes(db_session):
    """A tz-aware, not-yet-expired token must authenticate normally."""
    from datetime import timezone

    user = await _make_user(db_session)
    api_token = APIToken(
        user_id=user.id, name="aware-valid",
        token_hash=pwd_context.hash("aware-valid-token"),
        permissions="cmdb_read", is_active=True,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db_session.add(api_token)
    await db_session.commit()
    resolved = await check_api_token_cmdb_permission("aware-valid-token", db_session)
    assert resolved.id == user.id


@pytest.mark.asyncio
async def test_unknown_token_falls_back_to_jwt(db_session):
    # A token that matches no API-token row falls through to JWT auth, which
    # raises 401 for a bogus bearer token.
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        await check_api_token_cmdb_permission("not-a-real-token", db_session)
