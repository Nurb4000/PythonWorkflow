"""
Regression tests for findings #2: changing a password must invalidate every
session/token issued before that moment.

Three token families must be retired on password change:
- access tokens (stateless JWTs): verify_token rejects any token whose ``iat``
  is earlier than the user's ``password_changed_at``;
- refresh tokens: all active rows for the user are deactivated;
- API tokens: all of the user's APIToken rows are set is_active=False.
"""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models.auth import User, APIToken, RefreshToken
from app.services.auth_service import auth_service, pwd_context, _utcnow


async def _make_user(db, role="user"):
    user = User(username=f"pc_{role}", email=f"{role}@pc.test",
                password_hash=pwd_context.hash("strongpassword123"),
                role=role, is_active=True)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def test_create_access_token_stamps_iat():
    """Tokens now carry an ``iat`` claim so they can be compared against the
    user's password_changed_at marker (findings #2)."""
    token = auth_service.create_access_token({"sub": "1", "role": "user"})
    payload = auth_service.decode_token(token)
    assert payload is not None
    assert "iat" in payload


@pytest.mark.asyncio
async def test_verify_token_rejects_token_issued_before_password_change(db_session):
    """A token minted before the password was last changed is revoked even
    though its jti is not in the blocklist (findings #2)."""
    user = await _make_user(db_session)

    # Password "changed" 1 minute ago.
    ago = _utcnow() - timedelta(minutes=1)
    user.password_changed_at = ago
    await db_session.commit()

    # Token minted before the change (iat < password_changed_at).
    old_token = auth_service.create_access_token(
        {"sub": str(user.id), "role": user.role, "username": user.username}
    )
    assert await auth_service.verify_token(db_session, old_token) is None

    # A token minted after the change still verifies.
    new_token = auth_service.create_access_token(
        {"sub": str(user.id), "role": user.role, "username": user.username}
    )
    payload = await auth_service.verify_token(db_session, new_token)
    assert payload is not None
    assert payload["sub"] == str(user.id)


@pytest.mark.asyncio
async def test_verify_token_accepts_when_no_password_change_marker(db_session):
    """With no password_changed_at set (the common case), tokens verify as
    before regardless of iat."""
    user = await _make_user(db_session)
    token = auth_service.create_access_token(
        {"sub": str(user.id), "role": user.role, "username": user.username}
    )
    payload = await auth_service.verify_token(db_session, token)
    assert payload is not None


@pytest.mark.asyncio
async def test_change_password_revokes_refresh_and_api_tokens(db_session):
    """The change_password endpoint retires refresh tokens and deactivates API
    tokens for the user (findings #2)."""
    from app.api.auth import change_password

    user = await _make_user(db_session)

    # Seed a refresh token + an active API token.
    raw_refresh = await auth_service.issue_refresh_token(db_session, user.id)
    db.add(
        APIToken(
            user_id=user.id,
            name="test-token",
            token_hash=pwd_context.hash("apitokensecret"),
            is_active=True,
        )
    )
    await db_session.commit()

    result = await change_password(
        {"old_password": "strongpassword123", "new_password": "brandnewpass999"},
        current_user=user,
        db=db_session,
    )
    assert result == {"message": "Password changed successfully"}

    # Marker set so previously-issued access tokens are now revoked.
    await db_session.refresh(user)
    assert user.password_changed_at is not None

    # Refresh token retired: rotation rejects it.
    rotated = await auth_service.rotate_refresh_token(db_session, raw_refresh)
    assert rotated is None

    # API token deactivated.
    row = await db_session.execute(
        select(APIToken).where(APIToken.user_id == user.id)
    )
    api_token = row.scalar_one()
    assert api_token.is_active is False


@pytest.mark.asyncio
async def test_change_password_rejects_wrong_old_password(db_session):
    from fastapi import HTTPException
    from app.api.auth import change_password

    user = await _make_user(db_session)
    with pytest.raises(HTTPException) as exc:
        await change_password(
            {"old_password": "wrongold", "new_password": "brandnewpass999"},
            current_user=user,
            db=db_session,
        )
    assert exc.value.status_code == 400
