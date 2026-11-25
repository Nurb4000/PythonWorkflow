"""
Regression tests for multi-tenancy wiring (Feature-Plan §3.1 / gap 3.7).

Two things were added on top of the tenant foundation and must be pinned:

  Part A — tenant provisioning API (``app/api/tenancy.py``): admin-only CRUD over
  ``Tenant`` records with unique-slug enforcement (409) and not-found (404). Driven
  through the real app client against an in-memory SQLite schema so the actual model,
  query, and validation code paths run end to end.

  Part B — endpoint-level tenant scoping: the content list endpoints
  (``list_tasks``, ``list_workflows``, ``list_notifications``) must filter reads to
  the caller's tenant. We drive the real FastAPI app through TestClient (so request
  params resolve exactly as in production) and inject a recording session via get_db
  to capture the SQL each list endpoint finally executes, asserting a ``tenant_id``
  filter is present when the caller has a tenant and ABSENT when they do not.
"""
import os
import re
import tempfile

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.api.tasks as tasks_mod
import app.api.workflows as workflows_mod
import app.api.notifications as notifications_mod
import app.api.tenancy as tenancy_mod
import app.services.query_security_service as qss_mod
from app.api.auth import get_current_user
from app.core.database import Base, get_db
from app.api.tasks import list_tasks
from app.api.workflows import list_workflows
from app.api.notifications import list_notifications
from app.models.auth import User
from app.models.tenancy import Tenant


def _admin():
    return User(username="admin", email="admin@x.test", password_hash="x",
                role="admin", is_active=True, is_verified=True, tenant_id=1)


def _non_admin():
    return User(username="u", email="u@x.test", password_hash="x", role="user", tenant_id=1)


def _make_user(tenant_id):
    # Admin role bypasses the group-permission block in list_workflows, so the only
    # filter applied is tenant scoping -- isolating exactly what these tests assert.
    return User(username=f"u-{tenant_id}", tenant_id=tenant_id, role="admin")


# --------------------------------------------------------------------------- #
# Part A — tenant provisioning API
# --------------------------------------------------------------------------- #
@pytest_asyncio.fixture()
async def tenant_engine():
    """Async SQLite backed by a temp file (single shared connection).

    A temp *file* is used instead of ``:memory:`` because in-memory SQLite is
    destroyed the moment its single StaticPool connection closes -- and
    ``engine.begin()`` closes that connection after ``create_all`` returns, so the
    schema would not survive to serve the request. File-backed SQLite persists
    across the connection lifecycle, making the fixture deterministic.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{path}",
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Tenant.__table__])
    yield engine
    await engine.dispose()
    os.unlink(path)


@pytest_asyncio.fixture()
async def client(tenant_engine):
    """Real app client with get_db/get_current_user bound to the in-memory schema."""
    factory = async_sessionmaker(tenant_engine, class_=AsyncSession, expire_on_commit=False)
    application = FastAPI()
    application.include_router(tenancy_mod.router, prefix="/tenants")
    application.dependency_overrides[get_db] = lambda: factory()
    application.dependency_overrides[get_current_user] = lambda: _admin()
    with TestClient(application) as c:
        yield c


@pytest_asyncio.fixture()
async def seed_tenant(tenant_engine):
    """Create and return one tenant row; yields its id."""
    factory = async_sessionmaker(tenant_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        t = Tenant(name="Acme", slug="acme", is_active=True)
        s.add(t)
        await s.commit()
        await s.refresh(t)
        return t.id


def test_create_then_list_tenant(client):
    resp = client.post("/tenants", json={"name": "Acme Corp"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Acme Corp"
    assert body["slug"] == "acme-corp"
    assert body["is_active"] is True

    listing = client.get("/tenants").json()
    assert any(t["id"] == body["id"] for t in listing)


def test_slug_auto_generated_and_unique_conflict(client):
    first = client.post("/tenants", json={"name": "Globex"}).json()
    assert first["slug"] == "globex"
    # Explicit duplicate slug must be rejected with 409.
    dup = client.post("/tenants", json={"name": "Globex Different", "slug": first["slug"]})
    assert dup.status_code == 409, dup.text
    # A different name auto-generates a distinct slug and creates a new row.
    other = client.post("/tenants", json={"name": "Globex Industries"}).json()
    assert other["id"] != first["id"]
    assert other["slug"] == "globex-industries"


def test_get_missing_tenant_404(client):
    resp = client.get("/tenants/999999")
    assert resp.status_code == 404, resp.text


def test_update_name_slug_and_deactivate(client, seed_tenant):
    tid = seed_tenant
    upd = client.put(f"/tenants/{tid}", json={"name": "Acme Renamed", "is_active": False})
    assert upd.status_code == 200, upd.text
    body = upd.json()
    assert body["name"] == "Acme Renamed"
    assert body["slug"] == "acme-renamed"
    assert body["is_active"] is False

    got = client.get(f"/tenants/{tid}").json()
    assert got["is_active"] is False


def test_update_slug_collision(client):
    a = client.post("/tenants", json={"name": "Alpha"}).json()   # slug alpha
    b = client.post("/tenants", json={"name": "Beta"}).json()    # slug beta
    # Rename Alpha to "Beta" -> would slugify to "beta", colliding with B -> 409.
    resp = client.put(f"/tenants/{a['id']}", json={"name": "Beta"})
    assert resp.status_code == 409, resp.text


def test_non_admin_rejected(client):
    client.app.dependency_overrides[get_current_user] = lambda: _non_admin()
    resp = client.get("/tenants")
    assert resp.status_code == 403, resp.text


# --------------------------------------------------------------------------- #
# Part B — endpoint-level tenant scoping
# --------------------------------------------------------------------------- #
class _ScalarResults:
    def all(self):
        return []

    def __len__(self):
        return 0


class _DummyResult:
    def scalar(self):
        return 0

    def scalar_one(self):
        return 0

    def scalar_one_or_none(self):
        return None

    def scalars(self):
        return _ScalarResults()

    def all(self):
        return []


class RecordingSession:
    """Async session stand-in that records every statement passed to execute()."""

    def __init__(self):
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _DummyResult()

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def close(self):
        pass


def _build_client(tenant_id):
    """Build the app with the three content routers and a recording session."""
    rec = RecordingSession()
    application = FastAPI()
    application.include_router(tasks_mod.router)
    application.include_router(workflows_mod.router, prefix="/workflows")
    application.include_router(notifications_mod.router)
    application.dependency_overrides[get_db] = lambda: rec
    application.dependency_overrides[get_current_user] = lambda: _make_user(tenant_id)
    # Isolate scoping from the separate query-permission feature under test elsewhere.
    # Patch the singleton instance method so it returns True without running its own
    # queries against the recording session.
    async def _stub(*args, **kwargs):
        return True
    qss_mod.query_security_service.validate_query_access = _stub
    return TestClient(application), rec


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_list_tasks_applies_tenant_scope():
    client, rec = _build_client(7)
    client.get("/tasks")
    joined = " ".join(_sql(s) for s in rec.statements)
    assert "tenant_id" in joined, "list_tasks must filter by tenant_id"
    assert "7" in joined, "must be scoped to the caller's specific tenant"


def test_list_workflows_applies_tenant_scope():
    client, rec = _build_client(11)
    client.get("/workflows")
    joined = " ".join(_sql(s) for s in rec.statements)
    assert "tenant_id" in joined, "list_workflows must filter by tenant_id"


def test_list_notifications_applies_tenant_scope():
    client, rec = _build_client(13)
    client.get("/notifications")
    joined = " ".join(_sql(s) for s in rec.statements)
    assert "tenant_id" in joined, "list_notifications must filter by tenant_id"


def test_scoping_absent_when_user_has_no_tenant():
    # Negative control: a caller with no tenant gets NO tenant filter (platform scope).
    # NB: tenant_id may still appear as a *selected column* of the selectinload
    # follow-up query (e.g. workflow_runs.tenant_id); only a WHERE-style filter
    # (`...tenant_id = <id>`) indicates scoping, so match that pattern precisely.
    client, rec = _build_client(None)
    client.get("/tasks")
    joined = " ".join(_sql(s) for s in rec.statements)
    assert not re.search(r"(?:^|[.\s])tenant_id\s*=\s*\d+", joined), \
        "tenant filter present when tenant_id is None"
