"""
Tests for the demo-data seed commit contract (plan item 7).

``seed_all_demo_data`` flushes every ``seed_*`` helper but must itself perform a
single atomic commit on success and a clean rollback on partial failure, so a
caller can never observe flushed-but-uncommitted demo data.

The leaf helpers are stubbed so these tests exercise *only* the commit/rollback
contract (the real seeding has its own unrelated emoji-encoding issues).
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import pytest

from app.models.auth import Group
from app.services import demo_data_service as dms


_counter = 0


async def _flush_marker(db: AsyncSession) -> int:
    global _counter
    _counter += 1
    grp = Group(name=f"marker-{_counter}", is_active=True)
    db.add(grp)
    await db.flush()
    return grp.id


def _patch_stubs(monkeypatch, fail_on: str | None = None):
    """Replace the six leaf seed helpers with stubs that each flush one marker
    Group and return compatible canned values. If ``fail_on`` is set, that helper
    raises instead (to exercise the rollback path)."""

    async def ok(db, extra=None):
        gid = await _flush_marker(db)
        return extra or {"ok": gid}

    def make(name):
        async def stub(db, *args):
            return await ok(db, extra={"name": name})
        return stub

    specs = {
        "_seed_categories": make("_seed_categories"),
        "_seed_services": make("_seed_services"),
        "_seed_groups": make("_seed_groups"),
        "seed_cmdb_demo_data": make("seed_cmdb_demo_data"),
        "seed_kb_demo_data": make("seed_kb_demo_data"),
        "seed_demo_form": make("seed_demo_form"),
    }
    for attr, fn in specs.items():
        if fail_on == attr:

            async def boom(db):
                raise RuntimeError("seed failed midway")

            monkeypatch.setattr(dms, attr, boom)
        else:
            monkeypatch.setattr(dms, attr, fn)


async def _count_group(db):
    return (await db.execute(select(func.count()).select_from(Group))).scalar()


@pytest.mark.asyncio
async def test_seed_all_demo_data_commits_its_own_data(db_session, db_engine, monkeypatch):
    """After seed_all_demo_data returns, the data is committed and visible from a
    *separate* session — proving the orchestrator commits internally rather than
    relying on an external commit_demo_data() call."""
    _patch_stubs(monkeypatch)

    result = await dms.seed_all_demo_data(db_session)
    assert result["categories"] and result["services"] and result["groups"]

    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as read_db:
        # Six stubs each flushed a marker Group; a committed batch is visible
        # outside the seeding transaction.
        assert await _count_group(read_db) == 6


@pytest.mark.asyncio
async def test_seed_all_demo_data_rolls_back_on_partial_failure(db_session, db_engine, monkeypatch):
    """If any seed helper fails midway, the whole batch is rolled back: a fresh
    session must see zero demo rows (no flushed-but-uncommitted partial state)."""
    _patch_stubs(monkeypatch, fail_on="seed_cmdb_demo_data")

    with pytest.raises(RuntimeError):
        await dms.seed_all_demo_data(db_session)

    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as read_db:
        # categories/services/groups flushed before the failure must be undone.
        assert await _count_group(read_db) == 0
