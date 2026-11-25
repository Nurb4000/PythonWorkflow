"""
Regression tests for findings #31 (admin "Create User" could not create elevated-role accounts).

Root cause: the self-service ``register`` endpoint downgrades any role outside
``_ALLOWED_SELF_REGISTER_ROLES`` ({"user"}) to "user". The admin "Create User" form
POSTs through register, so selecting staff/developer/admin was silently ignored and
the account was created as a restricted "user" — broken admin workflow + security
confusion (an admin may believe a "Developer" exists when it is really a "user").

Fix (findings #31): new admin-only ``POST /auth/users`` endpoint honors the requested
role directly. Admin-created accounts are trusted, so they start verified. Self-service
``register`` still downgrades to "user" (unchanged).

These tests call the endpoints directly with a fake db + monkeypatched auth_service.
"""
import pytest
from fastapi import HTTPException

from app.api.auth import create_user_account, register, get_current_admin
from app.services.auth_service import auth_service


class FakeUser:
    def __init__(self, uid=1, role="user", roles=None, is_verified=True):
        self.id = uid
        self.username = "newadmin"
        self.email = "newadmin@example.com"
        self.role = role
        self.roles = roles
        self.is_verified = is_verified


class FakeRequest:
    def __init__(self, data=None, url_root="http://testserver"):
        self._data = data or {}
        self.url_root = url_root

    async def json(self):
        return self._data


class FakeDB:
    async def execute(self, stmt):
        class R:
            def scalar_one_or_none(r):
                return None
        return R()

    async def commit(self):
        pass


def _admin(role="admin"):
    return FakeUser(uid=99, role=role)


# --- admin can create elevated-role accounts via the new endpoint --------------

@pytest.mark.parametrize("role", ["staff", "developer", "admin", "cmdb_manager", "user"])
async def test_admin_can_create_any_valid_role(role, monkeypatch):
    created = {}

    async def fake_create_user(db=None, **kwargs):
        created.update(kwargs)
        return FakeUser(uid=1, role=kwargs.get("role", "user"), is_verified=kwargs.get("is_verified", True))

    monkeypatch.setattr(auth_service, "create_user", fake_create_user)

    result = await create_user_account(
        FakeRequest(), "dev1", "dev1@example.com", "password123",
        role=role, admin_user=_admin(), db=FakeDB(),
    )

    assert result["user"]["role"] == role
    # Admin-created accounts are trusted -> start verified.
    assert created.get("is_verified") is True
    assert result["user"]["is_verified"] is True


async def test_admin_create_invalid_role_returns_400(monkeypatch):
    async def fake_create_user(db=None, **kwargs):
        return FakeUser(uid=1, role="user")

    monkeypatch.setattr(auth_service, "create_user", fake_create_user)

    with pytest.raises(HTTPException) as exc:
        await create_user_account(
            FakeRequest(), "bad1", "bad1@example.com", "password123",
            role="superuser", admin_user=_admin(), db=FakeDB(),
        )
    assert exc.value.status_code == 400
    assert "Invalid role" in exc.value.detail


# --- self-service register still downgrades elevated roles to "user" (unchanged)

async def test_register_still_downgrades_to_user(monkeypatch):
    created = {}

    async def fake_create_user(db=None, **kwargs):
        created.update(kwargs)
        return FakeUser(uid=1, role=kwargs.get("role", "user"), is_verified=False)

    monkeypatch.setattr(auth_service, "create_user", fake_create_user)

    result = await register(
        FakeRequest({"full_name": "X"}),
        "self1", "self1@example.com", "password123", role="admin", db=FakeDB(),
    )

    # Self-service registration is intentionally restricted to "user".
    assert created.get("role") == "user"
    assert result["user"]["role"] == "user"


# --- endpoint requires an admin ------------------------------------------------

async def test_get_current_admin_rejects_non_admin():
    with pytest.raises(HTTPException) as exc:
        await get_current_admin(user=_admin(role="user"))
    assert exc.value.status_code == 403
