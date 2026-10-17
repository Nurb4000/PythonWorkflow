"""
Regression tests for server-side JWT revocation / logout (feature gap #6).

Access tokens are stateless HS256 JWTs. To support logout we stamp each token
with a unique ``jti`` and record revoked ``jti`` values in the
``token_revocations`` blocklist table; ``verify_token`` rejects any token whose
jti is listed. These tests pin that behaviour end to end.
"""
import pytest

from app.models.auth import User, TokenRevocation
from app.services.auth_service import auth_service, pwd_context


async def _make_user(db, role="user"):
    user = User(username=f"rev_{role}", email=f"{role}@rev.test",
                password_hash=pwd_context.hash("strongpassword123"),
                role=role, is_active=True)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def test_create_access_token_stamps_unique_jti():
    t1 = auth_service.create_access_token({"sub": "1", "role": "user"})
    t2 = auth_service.create_access_token({"sub": "1", "role": "user"})
    j1 = auth_service.decode_token(t1)
    j2 = auth_service.decode_token(t2)
    assert j1 and j2
    assert "jti" in j1 and "jti" in j2
    assert j1["jti"] != j2["jti"]


def test_decode_token_rejects_bogus_token():
    assert auth_service.decode_token("not.a.jwt") is None


@pytest.mark.asyncio
async def test_verify_token_accepts_valid_token(db_session):
    await _make_user(db_session)
    token = auth_service.create_access_token({"sub": "1", "role": "user"})
    payload = await auth_service.verify_token(db_session, token)
    assert payload is not None
    assert payload["sub"] == "1"


@pytest.mark.asyncio
async def test_verify_token_rejects_revoked_token(db_session):
    await _make_user(db_session)
    token = auth_service.create_access_token({"sub": "1", "role": "user"})
    jti = auth_service.decode_token(token)["jti"]

    assert await auth_service.revoke_token(db_session, jti, reason="logout") is True
    # Idempotent: revoking again reports nothing new was written.
    assert await auth_service.revoke_token(db_session, jti) is False
    assert await auth_service.is_token_revoked(db_session, jti) is True

    payload = await auth_service.verify_token(db_session, token)
    assert payload is None


@pytest.mark.asyncio
async def test_verify_token_none_jti_never_revoked(db_session):
    # A token without a jti (e.g. hand-crafted, pre-feature) must still verify
    # rather than erroring on the revocation lookup.
    from jose import jwt
    from app.core.config import settings
    from datetime import datetime, timedelta

    token = jwt.encode(
        {"sub": "1", "exp": datetime.utcnow() + timedelta(hours=1)},
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    payload = await auth_service.verify_token(db_session, token)
    assert payload is not None


@pytest.mark.asyncio
async def test_get_current_user_rejects_revoked_token(db_session):
    from fastapi import HTTPException
    from app.api.auth import get_current_user

    user = await _make_user(db_session)
    token = auth_service.create_access_token(
        {"sub": str(user.id), "role": user.role, "username": user.username}
    )
    # Sanity: valid token resolves the user.
    assert (await get_current_user(token, db_session)).id == user.id

    # After logout (revocation) the same token is refused with 401.
    jti = auth_service.decode_token(token)["jti"]
    await auth_service.revoke_token(db_session, jti, reason="logout")
    with pytest.raises(HTTPException) as exc:
        await get_current_user(token, db_session)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_logout_endpoint_revokes_token(db_session):
    from app.api.auth import logout

    user = await _make_user(db_session)
    token = auth_service.create_access_token(
        {"sub": str(user.id), "role": user.role, "username": user.username}
    )
    result = await logout(token, db_session)
    assert result["success"] is True

    jti = auth_service.decode_token(token)["jti"]
    assert await auth_service.is_token_revoked(db_session, jti) is True
    # Token no longer verifies after logout.
    assert await auth_service.verify_token(db_session, token) is None


@pytest.mark.asyncio
async def test_logout_endpoint_is_idempotent(db_session):
    from app.api.auth import logout

    user = await _make_user(db_session)
    token = auth_service.create_access_token(
        {"sub": str(user.id), "role": user.role, "username": user.username}
    )
    first = await logout(token, db_session)
    second = await logout(token, db_session)
    assert first["success"] is True
    assert second["success"] is True  # no error, no duplicate-row violation


def test_ldap_router_can_import_create_access_token():
    """The ldap router does ``from app.api.auth import create_access_token``.
    This must resolve and mint a token carrying a jti (regression guard for the
    ImportError that previously crashed first-time LDAP login)."""
    from app.api.auth import create_access_token

    token = create_access_token({"sub": "9", "role": "user"})
    payload = auth_service.decode_token(token)
    assert payload is not None
    assert "jti" in payload
