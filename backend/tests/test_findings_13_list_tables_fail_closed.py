"""
Regression test for findings #13 (`list_tables` leaks the full catalog).

`list_tables` filtered by `get_allowed_tables`, but an *empty* allowed set was
treated as "no restriction" and fell through to return the entire table list —
so any user whose role had no RolePermission rows (e.g. a plain `user` whose role
lives only in the scalar `role` column) could enumerate every table, including
sensitive column names like `password_hash`.

Fix: an empty allowed set now fails closed and returns no tables.

The endpoint is called directly (bypassing FastAPI DI) so no live DB / auth
header is required.
"""
import pytest

from app.api import data_query as dq


TABLES = [
    {"table": "workflows", "columns": ["id", "name"]},
    {"table": "configuration_items", "columns": ["id", "password_hash"]},
    {"table": "users", "columns": ["id", "email"]},
]


@pytest.fixture()
def user():
    class FakeUser:
        role = "user"
    return FakeUser()


@pytest.fixture()
def patch_allowed(monkeypatch):
    async def fake(db, u):
        return fake.allowed
    async def set_allowed(allowed):
        fake.allowed = allowed
    import app.services.query_security_service as qss
    monkeypatch.setattr(qss.query_security_service, "get_allowed_tables", fake)
    return set_allowed


@pytest.fixture()
def patch_tables(monkeypatch):
    rows = TABLES
    async def fake(db):
        return rows
    monkeypatch.setattr(dq, "list_tables_with_fields", fake)


async def test_empty_allowed_set_returns_no_tables(user, patch_allowed, patch_tables):
    await patch_allowed([])
    result = await dq.list_tables(current_user=user, db=object())
    assert result["tables"] == []
    assert result["total"] == 0


async def test_restricted_set_returns_only_allowed_tables(user, patch_allowed, patch_tables):
    await patch_allowed(["workflows", "users"])
    result = await dq.list_tables(current_user=user, db=object())
    names = {t["table"] for t in result["tables"]}
    assert names == {"workflows", "users"}
    assert "configuration_items" not in names  # sensitive table excluded


async def test_all_granted_tables_returns_everything(user, patch_allowed, patch_tables):
    await patch_allowed(["workflows", "configuration_items", "users"])
    result = await dq.list_tables(current_user=user, db=object())
    assert result["total"] == len(TABLES)
