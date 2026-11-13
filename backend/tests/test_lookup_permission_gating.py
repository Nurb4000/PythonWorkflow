"""
Regression tests for findings #29: the free lookup directory endpoints
(`/lookup/users`, `/lookup/ci-items`, `/lookup/perform`) previously required only
authentication, so any authenticated user (even a low-priv portal `user`) could
enumerate the entire user directory incl. role, and the same unscoped pattern
applied to CI-item lookups.

The fix gates all three free endpoints on a role allowlist
(``["admin", "developer", "staff"]`` — matching tasks.py's permission model), while
leaving the internal form-resolution path (forms.py -> lookup_service.* methods)
available to every authenticated role. Gating is endpoint-only.

Tests assert: allowed roles reach the service; denied roles get 403 and never reach
the service; and the service methods themselves remain role-agnostic when called
directly (as form resolution does).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import app.api.lookup as lookup_mod
from app.api.lookup import search_users, search_ci_items, perform_lookup
from app.services.lookup_service import lookup_service

ALLOWED = ["admin", "developer", "staff"]
DENIED = ["user", "cmdb_manager"]


def _user(role):
    return SimpleNamespace(role=role)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ALLOWED)
async def test_search_users_allowed_roles(role):
    with patch.object(lookup_mod.lookup_service, "lookup_users", new=AsyncMock(return_value=[{"id": 1}])):
        resp = await search_users(q="a", field="username", limit=10, current_user=_user(role), db=AsyncMock())
    assert resp["results"] == [{"id": 1}]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", DENIED)
async def test_search_users_denied_roles(role):
    from fastapi import HTTPException
    with patch.object(lookup_mod.lookup_service, "lookup_users", new=AsyncMock()) as svc:
        with pytest.raises(HTTPException) as exc:
            await search_users(q="a", field="username", limit=10, current_user=_user(role), db=AsyncMock())
    assert exc.value.status_code == 403
    svc.assert_not_called()  # gating happens before the service is reached


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ALLOWED)
async def test_search_ci_items_allowed_roles(role):
    with patch.object(lookup_mod.lookup_service, "lookup_ci_items", new=AsyncMock(return_value=[{"id": 2}])):
        resp = await search_ci_items(q="a", type_key="server", field="name", limit=10, current_user=_user(role), db=AsyncMock())
    assert resp["results"] == [{"id": 2}]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", DENIED)
async def test_search_ci_items_denied_roles(role):
    from fastapi import HTTPException
    with patch.object(lookup_mod.lookup_service, "lookup_ci_items", new=AsyncMock()) as svc:
        with pytest.raises(HTTPException) as exc:
            await search_ci_items(q="a", type_key="server", field="name", limit=10, current_user=_user(role), db=AsyncMock())
    assert exc.value.status_code == 403
    svc.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ALLOWED)
async def test_perform_lookup_allowed_roles(role):
    with patch.object(lookup_mod.lookup_service, "perform_lookup", new=AsyncMock(return_value={"id": 3})):
        resp = await perform_lookup(lookup_config={"target_type": "users"}, search_value="ali", current_user=_user(role), db=AsyncMock())
    assert resp == {"id": 3}


@pytest.mark.asyncio
@pytest.mark.parametrize("role", DENIED)
async def test_perform_lookup_denied_roles(role):
    from fastapi import HTTPException
    with patch.object(lookup_mod.lookup_service, "perform_lookup", new=AsyncMock()) as svc:
        with pytest.raises(HTTPException) as exc:
            await perform_lookup(lookup_config={"target_type": "users"}, search_value="ali", current_user=_user(role), db=AsyncMock())
    assert exc.value.status_code == 403
    svc.assert_not_called()


@pytest.mark.asyncio
async def test_internal_lookup_users_unaffected_by_endpoint_gating():
    """Form resolution calls the service method directly; it must stay role-agnostic."""
    fake_user = SimpleNamespace(id=1, username="alice", email="a@x.test", full_name="Alice", role="user")
    fake_result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [fake_user]))
    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(return_value=fake_result)

    results = await lookup_service.lookup_users(fake_db, "username", "ali", 10)
    assert results == [{
        "id": 1, "username": "alice", "email": "a@x.test",
        "full_name": "Alice", "role": "user",
    }]
