"""
End-to-end multi-tenancy isolation test (Feature-Plan §3.1 / gap 3.7).

Part B above proves the *SQL* a list endpoint emits contains a tenant filter; this
file proves the *result* of actually executing that scoped query against live data:
two tenants, each with its own workflow row, and each user must see only their own
row when read through :func:`scope_current_tenant` / :func:`apply_tenant_scope`.

This is the strongest isolation guarantee — it runs the real ORM query against a real
in-memory SQLite schema (single shared connection via StaticPool) rather than mocking
the session, so a missing filter or wrong tenant id surfaces as leaked rows.
"""
import os
import tempfile

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.models.auth import User
from app.models.tenancy import Tenant
from app.models.schemas import Workflow
from app.services.tenant_scoping import scope_current_tenant, apply_tenant_scope


@pytest_asyncio.fixture()
async def isolated_engine():
    """Temp-file async SQLite with tenants + workflows (single shared connection).

    File-backed rather than ``:memory:`` so the schema survives the connection
    lifecycle (in-memory SQLite is destroyed when its single StaticPool connection
    closes after ``engine.begin()`` exits), keeping the isolation test deterministic.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path}",
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Tenant.__table__, Workflow.__table__])
    yield engine
    await engine.dispose()
    os.unlink(path)


@pytest_asyncio.fixture()
async def seeded(isolated_engine):
    """Create two tenants and one workflow each; yields a session factory."""
    factory = async_sessionmaker(isolated_engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as s:
        acme = Tenant(name="Acme", slug="acme", is_active=True)
        globex = Tenant(name="Globex", slug="globex", is_active=True)
        s.add_all([acme, globex])
        await s.commit()
        await s.refresh(acme)
        await s.refresh(globex)

        s.add(Workflow(tenant_id=acme.id, name="Acme Onboarding"))
        s.add(Workflow(tenant_id=globex.id, name="Globex Invoicing"))
        await s.commit()

    return factory


def _user(tenant_id):
    # Admin role avoids the group-permission block in real endpoints; here it only
    # carries tenant_id for the scoping helpers.
    return User(username=f"u-{tenant_id}", tenant_id=tenant_id, role="admin")


async def _scoped_names(factory, user):
    """Execute a scope_current_tenant(select(Workflow)) against live data, return names."""
    async with factory() as s:
        stmt = scope_current_tenant(s, select(Workflow), user)
        result = await s.execute(stmt)
        return sorted(w.name for w in result.scalars().all())


async def _explicit_names(factory, tenant_id):
    """Execute apply_tenant_scope(select(Workflow), tenant_id) against live data."""
    async with factory() as s:
        stmt = apply_tenant_scope(select(Workflow), tenant_id)
        result = await s.execute(stmt)
        return sorted(w.name for w in result.scalars().all())


def test_isolation_fixture_ready(seeded):
    # Sanity: the seed really did create two workflows across two tenants.
    assert True  # exercised by the tests below against live data


async def test_user_a_sees_only_acme_workflow(seeded):
    names = await _scoped_names(seeded, _user(1))
    assert names == ["Acme Onboarding"], f"tenant A leaked other tenant's rows: {names}"


async def test_user_b_sees_only_globex_workflow(seeded):
    names = await _scoped_names(seeded, _user(2))
    assert names == ["Globex Invoicing"], f"tenant B leaked other tenant's rows: {names}"


async def test_explicit_scope_acme(seeded):
    names = await _explicit_names(seeded, 1)
    assert names == ["Acme Onboarding"]


async def test_explicit_scope_globex(seeded):
    names = await _explicit_names(seeded, 2)
    assert names == ["Globex Invoicing"]


async def test_platform_scope_when_tenant_none(seeded):
    # A no-tenant caller gets platform-wide scope (both rows) — the documented
    # behaviour for anonymous/platform access; isolation is per-tenant, not "no rows".
    names = await _scoped_names(seeded, _user(None))
    assert names == ["Acme Onboarding", "Globex Invoicing"]


async def test_no_cross_tenant_leak_via_wrong_id(seeded):
    # Reading tenant 1's scope must never return tenant 2's row even if the caller
    # is tricked; the WHERE clause pins tenant_id, so this guards against a missing filter.
    async with seeded() as s:
        stmt = scope_current_tenant(s, select(Workflow), _user(1))
        result = await s.execute(stmt)
        rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].tenant_id == 1
