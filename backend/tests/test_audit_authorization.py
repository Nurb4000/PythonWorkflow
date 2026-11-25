"""
Regression tests for findings #27: the audit endpoints must be authorization-gated.

Previously ``GET /audit/{entity_type}/{entity_id}`` and
``GET /audit/user/{user_id}`` required only ``get_current_user``, so any
authenticated user could enumerate the full change history of any object (incl.
``changes`` JSON, acting user, timestamps) or the complete activity history of
any user (logins, role changes, password updates, deletions). Both endpoints are
now gated behind ``get_current_admin`` — consistent with the audit-log endpoint
in ``api/admin.py``.

Tests cover:
  * the ``get_current_admin`` dependency (403 for non-admin, pass-through for admin);
  * both endpoints returning entries when called as admin;
  * a FastAPI-level integration check that a non-admin is rejected with 403 and an
    admin succeeds.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import audit
from app.api.auth import get_current_admin


class _FakeUser:
    def __init__(self, role, uid=7):
        self.role = role
        self.id = uid
        self.roles = []
        self.username = f"user{uid}"


ADMIN = _FakeUser("admin", uid=1)


class _FakeEntry:
    def to_dict(self):
        return {"id": 1, "entity_type": "workflow", "entity_id": 5, "action": "update"}


def _fake_entries():
    return [_FakeEntry()]


# --------------------------------------------------------------------------- #
# Part A: get_current_admin dependency (the actual security control)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_get_current_admin_passes_through_for_admin():
    assert await get_current_admin(ADMIN) is ADMIN


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["user", "developer", "cmdb_manager", "staff"])
async def test_get_current_admin_rejects_non_admin(role):
    from fastapi import HTTPException
    user = _FakeUser(role, uid=2)
    with pytest.raises(HTTPException) as exc:
        await get_current_admin(user)
    assert exc.value.status_code == 403


# --------------------------------------------------------------------------- #
# Part B: endpoint wiring (service monkeypatched; no DB needed)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_entity_endpoint_returns_entries_as_admin(monkeypatch):
    async def fake_get_audit_trail(db, entity_type, entity_id=None, user_id=None, limit=100):
        return _fake_entries()

    monkeypatch.setattr(audit.audit_service, "get_audit_trail", fake_get_audit_trail)

    resp = await audit.get_entity_audit_trail(
        "workflow", 5, limit=10, current_user=ADMIN, db=None
    )
    assert resp["entity_type"] == "workflow"
    assert resp["total"] == 1
    assert resp["entries"][0]["action"] == "update"


@pytest.mark.asyncio
async def test_user_endpoint_returns_entries_as_admin(monkeypatch):
    async def fake_get_audit_trail(db, entity_type, entity_id=None, user_id=None, limit=100):
        return _fake_entries()

    monkeypatch.setattr(audit.audit_service, "get_audit_trail", fake_get_audit_trail)

    resp = await audit.get_user_audit_trail(
        42, limit=10, current_user=ADMIN, db=None
    )
    assert resp["user_id"] == 42
    assert resp["total"] == 1


# --------------------------------------------------------------------------- #
# Part C: FastAPI integration — non-admin rejected, admin allowed
# --------------------------------------------------------------------------- #
@pytest.fixture
def app(monkeypatch):
    async def fake_get_audit_trail(db, entity_type, entity_id=None, user_id=None, limit=100):
        return _fake_entries()

    monkeypatch.setattr(audit.audit_service, "get_audit_trail", fake_get_audit_trail)

    application = FastAPI()
    application.include_router(audit.router)
    application.dependency_overrides.clear()
    application.dependency_overrides[audit.get_db] = lambda: None
    return application


def test_integration_entity_endpoint_rejects_non_admin(app):
    # Override the inner dependency so the real get_current_admin role check runs
    # and must reject the non-admin user with 403.
    from app.api.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _FakeUser("user", uid=9)
    client = TestClient(app)
    resp = client.get("/audit/workflows/5")
    assert resp.status_code == 403


def test_integration_entity_endpoint_ok_as_admin(app):
    from app.api.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: ADMIN
    client = TestClient(app)
    resp = client.get("/audit/workflows/5")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


def test_integration_user_endpoint_rejects_non_admin(app):
    from app.api.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: _FakeUser("developer", uid=9)
    client = TestClient(app)
    resp = client.get("/audit/user/42")
    assert resp.status_code == 403
