"""
Regression tests for findings #4: API-token verification was O(n) bcrypt per
request — ``verify_api_token`` / ``check_api_token_cmdb_permission`` iterated
*every* active APIToken and bcrypt-verified each. With bcrypt at cost 12 (~100ms+)
and N active tokens, each API-token request cost O(N) slow hashes → a cheap CPU
DoS an attacker could trigger on any API-token-authenticated endpoint.

Fix: store a deterministic HMAC-SHA256 index of the plaintext token
(``token_index``; same pattern as the refresh-token ``token_index``) and look the
presented token up by that index (single indexed read), then confirm with ONE
bcrypt check. Per-request verification is now O(log n) instead of O(n).

These tests are self-contained (in-memory SQLite + a fresh async engine) so they
run anywhere without a live PostgreSQL, while exercising the real
``create_api_token`` / ``verify_api_token`` code paths. ``expires_at`` is nulled
after creation to avoid SQLite's naive-datetime round-trip tripping the unrelated
tz-aware/naive expiry comparison (that comparison uses Postgres timestamptz in
production, where it is fine).
"""
import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.core.database import Base
from app.models.auth import APIToken, User
from app.services.auth_service import auth_service, refresh_token_index, pwd_context


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _make_user(db, role="user", uid="a"):
    email = f"{uid}@it.test"
    db.add(User(username=f"it{uid}", email=email,
                password_hash=pwd_context.hash("strongpassword123"),
                role=role, is_active=True))
    await db.commit()
    u = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    return u


async def _issue_token(db, user, perms=("cmdb_read",)):
    """Create a real API token, then null its expiry to avoid the SQLite tz artifact."""
    res = await auth_service.create_api_token(db, user.id, name="t", permissions=list(perms))
    token = res["token"]
    api_token = res["api_token"]
    api_token.expires_at = None
    await db.commit()
    return token, api_token


@pytest.mark.asyncio
async def test_create_api_token_populates_index(db):
    """New tokens carry a 64-char HMAC index for lookup (findings #4)."""
    user = await _make_user(db)
    token, api_token = await _issue_token(db, user)
    assert api_token.token_index is not None
    assert len(api_token.token_index) == 64
    # The stored index must equal refresh_token_index of the plaintext token.
    assert api_token.token_index == refresh_token_index(token)


@pytest.mark.asyncio
async def test_verify_api_token_valid_returns_user(db):
    """A correctly-issued token is resolved by indexed lookup + one bcrypt check."""
    user = await _make_user(db)
    token, _ = await _issue_token(db, user)
    verified = await auth_service.verify_api_token(db, token)
    assert verified is not None
    assert verified.id == user.id


@pytest.mark.asyncio
async def test_verify_api_token_unknown_returns_none(db):
    """A token with no matching index returns None (no scan, no false match)."""
    await _make_user(db)
    assert await auth_service.verify_api_token(db, "does-not-exist") is None


@pytest.mark.asyncio
async def test_verify_api_token_wrong_plaintext_returns_none(db):
    """Index matches but bcrypt fails → None (defense in depth confirms the hash)."""
    user = await _make_user(db)
    _, api_token = await _issue_token(db, user)
    # Craft a token whose index matches api_token's, but whose plaintext is wrong.
    fake_plaintext = "wrong-plaintext"
    indexed_by_fake = refresh_token_index(fake_plaintext)
    assert indexed_by_fake != api_token.token_index  # sanity: different plaintext → diff index
    # Force an index collision by overwriting the stored index to the fake's, then
    # verify with the fake plaintext: lookup finds the row, bcrypt must reject it.
    api_token.token_index = indexed_by_fake
    await db.commit()
    assert await auth_service.verify_api_token(db, fake_plaintext) is None


@pytest.mark.asyncio
async def test_verify_is_single_indexed_lookup(db, monkeypatch):
    """Verification performs exactly one indexed read (not a full-table scan)."""
    user = await _make_user(db)
    token, _ = await _issue_token(db, user)

    calls = {"count": 0}
    real_execute = db.execute

    async def counting_execute(stmt, *a, **k):
        text = str(stmt)
        if "token_index" in text and "api_tokens" in text:
            calls["count"] += 1
        return await real_execute(stmt, *a, **k)

    monkeypatch.setattr(db, "execute", counting_execute)
    await auth_service.verify_api_token(db, token)
    assert calls["count"] == 1  # one indexed lookup, not O(n) scans


@pytest.mark.asyncio
async def test_multiple_tokens_verify_with_one_lookup_each(db):
    """With N tokens, verifying one still does a single indexed read (no O(n))."""
    u1 = await _make_user(db, uid="a")
    u2 = await _make_user(db, uid="b")
    t1, _ = await _issue_token(db, u1)
    t2, _ = await _issue_token(db, u2)

    indexed_reads = {"count": 0}
    real_execute = db.execute

    async def counting_execute(stmt, *a, **k):
        if "token_index" in str(stmt) and "api_tokens" in str(stmt):
            indexed_reads["count"] += 1
        return await real_execute(stmt, *a, **k)

    db.execute = counting_execute  # type: ignore
    await auth_service.verify_api_token(db, t1)
    await auth_service.verify_api_token(db, t2)
    assert indexed_reads["count"] == 2  # one per token regardless of N=2


@pytest.mark.asyncio
async def test_check_api_token_cmdb_permission_valid(db):
    """CMDB dependency resolves a valid token via the indexed lookup (findings #4)."""
    from app.api import auth as auth_module

    user = await _make_user(db, role="user")
    token, _ = await _issue_token(db, user, perms=["cmdb_read"])
    result = await auth_module.check_api_token_cmdb_permission(token, db, require_write=False)
    assert result.id == user.id


@pytest.mark.asyncio
async def test_check_api_token_cmdb_permission_invalid_falls_back(db, monkeypatch):
    """An unknown token skips the (empty) indexed match and falls back to JWT auth."""
    from app.api import auth as auth_module

    seen = {}

    async def fake_get_current_user(token, db):
        seen["called"] = True
        return None

    monkeypatch.setattr(auth_module, "get_current_user", fake_get_current_user)
    result = await auth_module.check_api_token_cmdb_permission("not-a-real-token", db, require_write=False)
    assert seen.get("called") is True
    assert result is None
