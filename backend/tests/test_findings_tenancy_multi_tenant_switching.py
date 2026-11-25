"""
Regression tests for multi-tenant switching (Feature-Plan §3.1 extension).

A user may belong to more than one tenant. Three things are pinned here:

  1. Membership resolution -- :func:`member_tenant_ids` / :func:`list_member_tenants`
     must return the user's *default* tenant (``users.tenant_id``, implicit membership,
     no backfill) UNION any additional tenants recorded in ``user_tenants``.

  2. Active-tenant scoping -- :func:`scope_current_tenant` must scope to the request's
     active tenant (published into ``ACTIVE_TENANT_ID_CTX``) when one is selected, and
     fall back to the user's default tenant otherwise. This is what makes per-request
     tenant switching isolate data correctly without touching any content endpoint.

  3. Membership management API -- the admin endpoints on ``app.api.tenancy`` that add /
     list / remove a user's membership in a tenant, with 404 for unknown tenant/user and
     403 for non-admins.

Driven through the real FastAPI app against a temp-file SQLite schema (users + tenants
+ user_tenants) so the actual model, query, and validation paths run end to end.
"""
import os
import tempfile

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.api.tenancy as tenancy_mod
from app.api.auth import get_current_user
from app.core.database import Base, get_db
from app.models.auth import User, user_tenants
from app.models.tenancy import Tenant
from app.services.tenant_scoping import (
    ACTIVE_TENANT_ID_CTX,
    member_tenant_ids,
    list_member_tenants,
    scope_current_tenant,
    set_active_tenant_id,
)


def _admin(tenant_id=1):
    return User(username="admin", email="admin@x.test", password_hash="x",
                role="admin", is_active=True, is_verified=True, tenant_id=tenant_id)


def _plain_user():
    return User(username="u", email="u@x.test", password_hash="x",
                role="user", is_active=True, is_verified=True, tenant_id=1)


@pytest_asyncio.fixture()
async def engine():
    """Temp-file SQLite with users + tenants + user_tenants (single shared connection)."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    eng = create_async_engine(
        f"sqlite+aiosqlite:///{path}", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[User.__table__, Tenant.__table__, user_tenants],
        )
    yield eng
    await eng.dispose()
    os.unlink(path)


@pytest_asyncio.fixture()
async def seeded(engine):
    """Create two tenants + one user (default tenant 1) and return a session factory."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        t1 = Tenant(name="Acme", slug="acme", is_active=True)
        t2 = Tenant(name="Globex", slug="globex", is_active=True)
        s.add_all([t1, t2])
        await s.commit()
        await s.refresh(t1)
        await s.refresh(t2)

        u = User(username="alice", email="alice@x.test", password_hash="x",
                 role="user", is_active=True, is_verified=True, tenant_id=t1.id)
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return factory, t1.id, t2.id, u.id


# --------------------------------------------------------------------------- #
# 1. Membership resolution
# --------------------------------------------------------------------------- #
async def test_member_tenant_ids_includes_default_and_join(seeded):
    factory, t1_id, t2_id, u_id = seeded
    async with factory() as s:
        u = (await s.execute(select(User).where(User.id == u_id))).scalar_one()
        # Default tenant only at first.
        assert await member_tenant_ids(s, u) == {t1_id}
        assert await list_member_tenants(s, u) == [{"id": t1_id, "name": "Acme",
                                                    "slug": "acme", "is_active": True}]

        # Add the second tenant via the join table.
        await s.execute(user_tenants.insert().values(user_id=u_id, tenant_id=t2_id, is_admin=False))
        await s.commit()

        u2 = (await s.execute(select(User).where(User.id == u_id))).scalar_one()
        assert await member_tenant_ids(s, u2) == {t1_id, t2_id}
        names = {t["name"] for t in await list_member_tenants(s, u2)}
        assert names == {"Acme", "Globex"}


async def test_scope_current_tenant_honors_active_tenant(seeded):
    """Active tenant overrides the default; absent active tenant falls back to default."""
    from sqlalchemy.dialects import postgresql

    def _sql(stmt) -> str:
        return str(stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    factory, t1_id, t2_id, u_id = seeded
    async with factory() as s:
        u = (await s.execute(select(User).where(User.id == u_id))).scalar_one()

        # No active tenant selected -> scopes to the default (t1).
        set_active_tenant_id(None)
        assert f"{User.__tablename__}.tenant_id = {t1_id}" in _sql(
            scope_current_tenant(s, select(User).where(User.id == u_id), u))
        assert f"{User.__tablename__}.tenant_id = {t2_id}" not in _sql(
            scope_current_tenant(s, select(User).where(User.id == u_id), u))

        # Active tenant selected -> scopes to t2 instead of the default t1.
        set_active_tenant_id(t2_id)
        scoped2 = _sql(scope_current_tenant(s, select(User).where(User.id == u_id), u))
        assert f"{User.__tablename__}.tenant_id = {t2_id}" in scoped2
        assert f"{User.__tablename__}.tenant_id = {t1_id}" not in scoped2


# --------------------------------------------------------------------------- #
# 2. Membership management API
# --------------------------------------------------------------------------- #
@pytest_asyncio.fixture()
async def client(seeded, engine):
    factory, _, _, _ = seeded
    application = FastAPI()
    application.include_router(tenancy_mod.router, prefix="/tenants")
    application.dependency_overrides[get_db] = lambda: factory()
    application.dependency_overrides[get_current_user] = _admin
    with TestClient(application) as c:
        yield c


async def _seed_tenant_row(engine, tid):
    """Ensure a tenant row exists for the id returned by the fixture (idempotent)."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        t = Tenant(name="Acme", slug="acme", is_active=True)
        s.add(t)
        await s.commit()
        await s.refresh(t)
        return t.id


def test_add_list_remove_member(client, seeded, engine):
    factory, t1_id, t2_id, u_id = seeded

    # Admin lists members of tenant 1 -> just alice (default member).
    resp = client.get(f"/tenants/{t1_id}/members")
    assert resp.status_code == 200, resp.text
    assert [m["id"] for m in resp.json()] == [u_id]

    # Admin lists members of tenant 2 -> empty (alice not yet a member).
    resp = client.get(f"/tenants/{t2_id}/members")
    assert resp.status_code == 200, resp.text
    assert resp.json() == []

    # Add alice to tenant 2.
    resp = client.post(f"/tenants/{t2_id}/members", json={"user_id": u_id})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"user_id": u_id, "tenant_id": t2_id, "added": True}

    # Idempotent: adding again still succeeds.
    resp = client.post(f"/tenants/{t2_id}/members", json={"user_id": u_id})
    assert resp.status_code == 200, resp.text

    # Now tenant 2 lists alice.
    resp = client.get(f"/tenants/{t2_id}/members")
    assert resp.status_code == 200, resp.text
    assert [m["id"] for m in resp.json()] == [u_id]

    # Remove alice from tenant 2.
    resp = client.delete(f"/tenants/{t2_id}/members/{u_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"user_id": u_id, "tenant_id": t2_id, "removed": True}

    # Tenant 2 is empty again.
    resp = client.get(f"/tenants/{t2_id}/members")
    assert resp.json() == []


def test_add_member_unknown_tenant_404(client):
    resp = client.post("/tenants/999999/members", json={"user_id": 1})
    assert resp.status_code == 404, resp.text


def test_add_member_unknown_user_404(client, seeded):
    _, t1_id, _, _ = seeded
    resp = client.post(f"/tenants/{t1_id}/members", json={"user_id": 999999})
    assert resp.status_code == 404, resp.text


def test_remove_member_not_a_member_409(client, seeded):
    _, t2_id, _, u_id = seeded
    resp = client.delete(f"/tenants/{t2_id}/members/{u_id}")
    assert resp.status_code == 409, resp.text


def test_membership_non_admin_rejected(client, seeded):
    client.app.dependency_overrides[get_current_user] = _plain_user
    resp = client.get("/tenants/1/members")
    assert resp.status_code == 403, resp.text
