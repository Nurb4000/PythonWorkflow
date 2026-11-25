"""
Regression tests for findings #37: webhook idempotency cache grew unbounded on
attacker-controlled keys -> memory/CPU exhaustion (DoS).

The bug: `app/api/webhooks.py` kept `_idempotency_cache` as a plain module-level
`dict` keyed on the client-supplied `X-Idempotency-Key` header, retained for 15 min,
pruned lazily (only when a request carried an idempotency key) by scanning **every**
held entry — O(N) — and never evicting on overflow. Entries were only ever added, so a
flood of unique keys grew the cache without bound within each window, and every
idempotency-keyed request paid O(N) scan cost (≈ O(N²) over a sustained flood). The
cache work also ran *before* `verify_webhook_secret()`, so unauthenticated callers
(bad/missing secret, rejected only later) could still drive cache writes and scans.

Fix (#37):
- `_idempotency_cache` is now an `OrderedDict` with a hard cap
  (`_IDEMPOTENCY_MAX_ENTRIES`). `_prune_idempotency_entries` drops expired entries and
  evicts oldest-first on overflow; `_record_idempotency` evicts oldest on insert. Since
  entries are inserted in monotonic-time order, the front is always the oldest -> O(1)
  eviction. N is bounded regardless of request pattern.
- The idempotency check now runs *after* `verify_webhook_secret()` so unauthenticated
  callers cannot drive cache growth / O(N) scans (defense in depth).

These tests are self-contained: in-memory SQLite (aiosqlite + StaticPool-equivalent)
with the real tables, monkeypatching the scheduler call and rate limiter, so no live
PostgreSQL is required.
"""
import time as _time

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.core.database import Base
from app.models.schemas import Workflow
import app.api.webhooks as wm


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        # Neutralize the real rate limiter (shared module state) so tests are isolated.
        wm._check_rate_limit = lambda key: None
        yield session
    await engine.dispose()


@pytest.fixture(autouse=True)
def _clean_cache():
    """Save/restore the shared module cache so tests never leak entries into each other."""
    saved = wm._idempotency_cache.copy()
    wm._idempotency_cache.clear()
    yield
    wm._idempotency_cache.clear()
    wm._idempotency_cache.update(saved)


class _FakeRun:
    def __init__(self, run_id):
        self.id = run_id


async def _seed_workflow(db, wf_id=1):
    db.add(Workflow(id=wf_id, name="wf37", is_active=True))
    await db.commit()


# --- unit: bounded cache behavior (no endpoint/DB needed) ------------------------

async def test_cache_stays_bounded_after_overflow(db):
    """Recording more than the cap keeps len == cap and evicts the oldest keys."""
    cap = wm._IDEMPOTENCY_MAX_ENTRIES
    for i in range(cap + 50):
        wm._record_idempotency(f"k{i}", i)

    assert len(wm._idempotency_cache) == cap
    # Oldest 50 evicted; newest retained.
    assert "k0" not in wm._idempotency_cache
    assert f"k{cap - 1}" in wm._idempotency_cache
    assert f"k{cap + 49}" in wm._idempotency_cache


async def test_record_evicts_oldest_on_each_insert(db):
    """Filling to the cap then adding one more evicts exactly the oldest entry."""
    cap = wm._IDEMPOTENCY_MAX_ENTRIES
    for i in range(cap):
        wm._record_idempotency(f"a{i}", i)
    assert len(wm._idempotency_cache) == cap

    wm._record_idempotency("a_new", 999)

    assert len(wm._idempotency_cache) == cap
    assert "a0" not in wm._idempotency_cache
    assert "a_new" in wm._idempotency_cache


async def test_expired_entries_pruned_on_access(db):
    """A prune drops entries older than the window but keeps recent ones."""
    now = _time.monotonic()
    wm._idempotency_cache["old"] = (now - 1000, 1)   # older than _IDEMPOTENCY_WINDOW
    wm._idempotency_cache["recent"] = (now, 2)

    wm._prune_idempotency_entries(now)

    assert "old" not in wm._idempotency_cache
    assert "recent" in wm._idempotency_cache


async def test_prune_keeps_cap_when_mixing_expired_and_overflow(db):
    """Prune drops expired first, then trims oldest to the cap even if already overfilled.

    In normal operation `_record_idempotency` caps the cache on insert, so this test
    overfills the dict directly (bypassing insert-time eviction) to exercise prune's
    overflow-eviction backstop: 5 stale + (cap + 5) fresh = cap + 10.
    """
    now = _time.monotonic()
    cap = wm._IDEMPOTENCY_MAX_ENTRIES
    for i in range(5):
        wm._idempotency_cache[f"stale{i}"] = (now - 2000, i)
    for i in range(cap + 5):
        wm._idempotency_cache[f"fresh{i}"] = (now, i)  # direct assign -> no eviction
    assert len(wm._idempotency_cache) == cap + 10

    wm._prune_idempotency_entries(now)

    # 5 stale dropped first, then 5 oldest fresh evicted to return to the cap.
    assert len(wm._idempotency_cache) == cap
    assert all(not k.startswith("stale") for k in wm._idempotency_cache)
    assert "fresh0" not in wm._idempotency_cache
    assert "fresh4" not in wm._idempotency_cache
    assert "fresh5" in wm._idempotency_cache
    assert f"fresh{cap + 4}" in wm._idempotency_cache


# --- integration: endpoint still idempotent, and now auth-gated -----------------

async def test_idempotent_replay_returns_cached_run(db, monkeypatch):
    """A valid key triggers once; a replay returns the same run without re-triggering."""
    await _seed_workflow(db)
    monkeypatch.setattr(wm.settings, "webhook_secret", "test-secret")

    calls = {"n": 0}

    async def fake_trigger(workflow_id, payload, auth_token=None):
        calls["n"] += 1
        return _FakeRun(run_id=100 + calls["n"])

    monkeypatch.setattr(wm.scheduler_service, "trigger_webhook", fake_trigger)

    r1 = await wm.webhook_trigger(
        workflow_id=1, payload={}, x_webhook_secret="test-secret",
        x_idempotency_key="k1", x_forwarded_for="1.2.3.4", db=db,
    )
    assert r1["success"] is True
    assert r1["run_id"] == 101
    # A fresh (non-replay) trigger does not flag idempotent=True.
    assert r1.get("idempotent") in (None, False)

    r2 = await wm.webhook_trigger(
        workflow_id=1, payload={}, x_webhook_secret="test-secret",
        x_idempotency_key="k1", x_forwarded_for="1.2.3.4", db=db,
    )
    assert r2["run_id"] == 101            # same cached run
    assert r2["idempotent"] is True       # flagged as replay
    assert calls["n"] == 1                # workflow triggered only once


async def test_replay_requires_valid_secret(db, monkeypatch):
    """Even with a cached key, a bad/missing secret is rejected before the replay.

    This asserts the defense-in-depth ordering (#37): the idempotency check now runs
    AFTER verify_webhook_secret(), so an unauthenticated caller cannot force a replay
    (or cache work) without a valid secret. Under the old code the replay ran first.
    """
    await _seed_workflow(db)
    monkeypatch.setattr(wm.settings, "webhook_secret", "test-secret")
    wm._record_idempotency("cached-key", 555)  # pre-seed a cached run

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await wm.webhook_trigger(
            workflow_id=1, payload={}, x_webhook_secret="wrong-secret",
            x_idempotency_key="cached-key", x_forwarded_for="1.2.3.4", db=db,
        )
    assert exc.value.status_code in (401, 403)


async def test_missing_secret_rejected_before_cache_work(db, monkeypatch):
    """No secret at all -> 401 even when an idempotency key is supplied."""
    await _seed_workflow(db)
    monkeypatch.setattr(wm.settings, "webhook_secret", "test-secret")

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await wm.webhook_trigger(
            workflow_id=1, payload={}, x_webhook_secret=None,
            x_idempotency_key="k9", x_forwarded_for="1.2.3.4", db=db,
        )
    assert exc.value.status_code == 401
