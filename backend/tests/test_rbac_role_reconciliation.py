"""
Regression tests for I8: dual-field RBAC (``role`` scalar vs ``roles`` array)
reconciliation.

The ``role`` scalar and the ``roles`` JSON array must never disagree. ``role``
is authoritative and always equals ``roles[0]``. This closes the demotion
bypass where an admin set ``role="user"`` while a stale ``"admin"`` lingered in
``roles`` and the OR-based ``has_role`` check still granted admin access.
"""
import pytest

from app.services.auth_service import auth_service, reconcile_role_roles, KNOWN_ROLES
from app.api.auth import has_role


# --- pure reconciliation helper -------------------------------------------------

def test_reconcile_role_derives_roles_from_primary():
    assert reconcile_role_roles("user", None) == ("user", ["user"])


def test_reconcile_primary_is_prepended_to_existing_roles():
    # role is authoritative: it becomes roles[0] while extra roles are preserved.
    assert reconcile_role_roles("developer", ["admin", "developer"]) == (
        "developer", ["developer", "admin"])


def test_reconcile_roles_only_promotes_first_as_primary():
    assert reconcile_role_roles(None, ["staff", "user"]) == ("staff", ["staff", "user"])


def test_reconcile_dedupes_roles():
    assert reconcile_role_roles("admin", ["admin", "user", "admin"]) == (
        "admin", ["admin", "user"])


@pytest.mark.parametrize("role,roles", [
    ("rogue", None),
    (None, ["admin", "rogue"]),
    ("bogus", ["bogus"]),
])
def test_reconcile_rejects_unknown_roles(role, roles):
    with pytest.raises(ValueError):
        reconcile_role_roles(role, roles)


# --- create_user consistency ----------------------------------------------------

@pytest.mark.asyncio
async def test_create_user_roles_consistent_with_role(db_session):
    for role in ("user", "admin", "developer", "cmdb_manager", "staff"):
        user = await auth_service.create_user(
            db_session, username=f"i8_{role}", email=f"{role}@i8.test",
            password="StrongPass1", role=role,
        )
        assert user.role == role
        assert user.roles == [role]
        assert user.roles[0] == user.role


# --- update_user: demotion bypass is closed -------------------------------------

@pytest.mark.asyncio
async def test_update_role_demotes_and_derives_roles(db_session):
    user = await auth_service.create_user(
        db_session, username="i8_admin", email="i8_admin@test.com",
        password="StrongPass1", role="admin",
    )
    assert has_role(user, "admin") is True

    # Demote via the primary role only — the stale "admin" must NOT linger.
    updated = await auth_service.update_user(db_session, user.id, role="user")
    assert updated.role == "user"
    assert updated.roles == ["user"]
    assert has_role(updated, "admin") is False


@pytest.mark.asyncio
async def test_update_role_authoritative_over_provided_array(db_session):
    user = await auth_service.create_user(
        db_session, username="i8_dev", email="i8_dev@test.com",
        password="StrongPass1", role="developer",
    )
    # Even if a caller sends a conflicting array, the primary role wins and is
    # placed first so the two fields stay consistent.
    updated = await auth_service.update_user(
        db_session, user.id, role="admin", roles=["admin", "developer"])
    assert updated.role == "admin"
    assert updated.roles[0] == "admin"
    assert "developer" in updated.roles  # extra role preserved


@pytest.mark.asyncio
async def test_update_roles_only_sets_primary_from_array(db_session):
    user = await auth_service.create_user(
        db_session, username="i8_staff", email="i8_staff@test.com",
        password="StrongPass1", role="user",
    )
    updated = await auth_service.update_user(
        db_session, user.id, roles=["staff", "user"])
    assert updated.role == "staff"
    assert updated.roles[0] == "staff"


@pytest.mark.asyncio
async def test_update_invalid_role_rejected(db_session):
    user = await auth_service.create_user(
        db_session, username="i8_bad", email="i8_bad@test.com",
        password="StrongPass1", role="user",
    )
    with pytest.raises(ValueError):
        await auth_service.update_user(db_session, user.id, role="superuser")
