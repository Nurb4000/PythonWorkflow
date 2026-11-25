"""
Regression tests for findings #31 (second #31): `/api/trigger/{workflow_id}`
(`external_trigger` in webhooks.py) API-key auth was permanently broken.

The endpoint hashed the presented `X-Api-Key` with an unsalted **SHA-256**
(`hashlib.sha256(x_api_key).hexdigest()`) and matched it against
``APIToken.token_hash`` — but tokens are stored with a **salted bcrypt** hash
(`auth_service.create_api_token` -> `pwd_context.hash(token)`). A salted bcrypt
hash and an unsalted SHA-256 hexdigest can never be equal, so the lookup always
returned no row and the endpoint returned ``401 Invalid API key`` for *every*
request — even with a valid key. It fails closed (no auth bypass), so it is not
directly exploitable, but it gives a false sense of authenticated API access and
breaks every integration relying on `/api/trigger`.

Fix (#31): verify the presented key with bcrypt via the shared indexed lookup
``auth_service.verify_api_token`` (single HMAC-indexed read + one bcrypt check),
which also handles tz-aware expiry. This mirrors how
``check_api_token_cmdb_permission`` / ``verify_api_token`` already authenticate.

These tests are self-contained: in-memory SQLite (aiosqlite) with the real
``api_tokens``/``users``/``workflows`` tables and the real
``create_api_token``/``verify_api_token`` code paths, so no live PostgreSQL is
required. ``expires_at`` is nulled after creation to avoid SQLite's naive-datetime
round-trip tripping the tz-aware expiry comparison (which uses Postgres
timestamptz in production).
"""
import types

import pytest
from sqlalchemy import select

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.core.database import Base
from app.models.auth import User
from app.models.schemas import Workflow
from app.services.auth_service import auth_service
import app.api.webhooks as webhooks_module


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        # Rate limiting touches shared state / a real store; neutralize it so the
        # endpoint logic under test is what runs.
        webhooks_module._check_rate_limit = lambda key: None
        yield session
    await engine.dispose()


class _FakeRun:
    def __init__(self, run_id):
        self.id = run_id


@pytest.fixture
async def fake_scheduler(monkeypatch):
    """Replace the scheduler used by external_trigger with a stub returning a run."""

    class _FakeScheduler:
        async def trigger_external_api(self, workflow_id, input_data, api_key=None):
            return _FakeRun(run_id=999)

    fake = _FakeScheduler()
    monkeypatch.setattr(webhooks_module, "scheduler_service", fake)
    return fake


async def _make_user(db):
    db.add(User(username="api31_test", email="api31@test",
                password_hash="x", role="user", is_active=True))
    await db.commit()
    u = (await db.execute(select(User).where(User.username == "api31_test"))).scalar_one_or_none()
    return u


async def _make_workflow(db, wf_id=1):
    db.add(Workflow(id=wf_id, name="wf31", is_active=True))
    await db.commit()


async def _issue_token(db, user):
    """Issue a real bcrypt+HMAC-index API token; null expiry for SQLite's tz artifact."""
    res = await auth_service.create_api_token(db, user.id, name="t", permissions=["workflow_trigger"])
    token = res["token"]
    api_token = res["api_token"]
    api_token.expires_at = None
    await db.commit()
    return token


async def _call(db, x_api_key, workflow_id=1):
    return await webhooks_module.external_trigger(
        workflow_id=workflow_id,
        input_data={},
        x_api_key=x_api_key,
        x_forwarded_for="1.2.3.4",
        request=None,
        db=db,
    )


@pytest.mark.asyncio
async def test_valid_api_key_authenticates(db, fake_scheduler):
    """A correctly-issued API key now authenticates (the core #31 regression).

    Before the fix the SHA-256-vs-bcrypt mismatch made this return 401 for every
    request; after, it succeeds because verify_api_token bcrypt-verifies the key.
    """
    user = await _make_user(db)
    token = await _issue_token(db, user)
    await _make_workflow(db)

    result = await _call(db, token)

    assert result["success"] is True
    assert result["run_id"] == 999
    assert result["workflow_id"] == 1


@pytest.mark.asyncio
async def test_wrong_api_key_is_401(db, fake_scheduler):
    """A malformed key authenticates against no stored token → 401."""
    user = await _make_user(db)
    await _issue_token(db, user)
    await _make_workflow(db)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await _call(db, "not-the-real-key")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_missing_api_key_is_401(db, fake_scheduler):
    """No X-Api-Key header → 401 Missing X-Api-Key header."""
    await _make_user(db)
    await _make_workflow(db)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await _call(db, None)
    assert exc.value.status_code == 401
    assert "Missing" in exc.value.detail


@pytest.mark.asyncio
async def test_inactive_token_is_401(db, fake_scheduler):
    """An inactive token must not authenticate."""
    from app.models.auth import APIToken
    from app.services.auth_service import pwd_context

    user = await _make_user(db)
    db.add(APIToken(
        user_id=user.id, name="inactive",
        token_hash=pwd_context.hash("inactive-key"),
        permissions="workflow_trigger", is_active=False,
    ))
    await db.commit()
    await _make_workflow(db)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await _call(db, "inactive-key")
    assert exc.value.status_code == 401
