"""
Regression tests for findings #26: the CSV export paths must not leak sensitive
columns and must enforce table-level RBAC.

Two controls are verified here:
  * a hard secret-column denylist (``strip_secret_export_columns``) that is
    applied on every export path regardless of caller or requested columns;
  * table-level view access (``validate_query_access``) enforced in both
    endpoints, matching the guard used by ``/data-query/build``.

These tests avoid a live PostgreSQL by faking the ORM row/result objects and
monkeypatching the security service, following the pattern in
``test_visual_query_field_filtering.py``.
"""
import pytest
from fastapi import HTTPException

from app.api import data_export
from app.services import data_query_service
from app.services.data_query_service import (
    export_table_to_csv,
    export_query_to_csv,
    strip_secret_export_columns,
)
from app.services.query_security_service import query_security_service


# --------------------------------------------------------------------------- #
# Pure denylist
# --------------------------------------------------------------------------- #
def test_strip_secret_export_columns_removes_sensitive_keeps_others():
    cols = ["id", "username", "password_hash", "ldap_dn", "custom_data", "token", "email"]
    out = strip_secret_export_columns(cols)
    assert out == ["id", "username", "email"]  # order preserved


def test_strip_secret_export_columns_is_idempotent():
    cols = ["id", "password_hash", "ldap_dn"]
    assert strip_secret_export_columns(strip_secret_export_columns(cols)) == ["id"]


# --------------------------------------------------------------------------- #
# Fakes for the table-export service path (no real DB needed)
# --------------------------------------------------------------------------- #
class _FakeCol:
    def __init__(self, name):
        self.name = name


class _FakeTable:
    def __init__(self, cols):
        self.columns = [_FakeCol(c) for c in cols]


class _FakeModel:
    def __init__(self, cols):
        self.__table__ = _FakeTable(cols)


class _FakeRow:
    def __init__(self, data):
        for k, v in data.items():
            setattr(self, k, v)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, stmt):  # noqa: ARG002 - statement is ignored by the fake
        return _FakeResult(self._rows)


_USER = type("User", (), {"id": 1, "role": "developer", "roles": []})()


def _patch_users_table(monkeypatch, cols):
    monkeypatch.setattr(
        data_query_service, "QUERYABLE_TABLES", {"users": (_FakeModel(cols), "Users")}
    )

    # select(model).limit(...) must not hit a real compiler; return a no-op
    # statement that _FakeDB.execute ignores.
    class _FakeSelectable:
        def limit(self, n):  # noqa: ARG003
            return self

    monkeypatch.setattr(data_query_service, "select", lambda *a, **k: _FakeSelectable())


# --------------------------------------------------------------------------- #
# export_table_to_csv
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_export_table_to_csv_strips_secrets_by_default(monkeypatch):
    cols = ["id", "username", "password_hash", "ldap_dn", "custom_data"]
    _patch_users_table(monkeypatch, cols)
    rows = [_FakeRow({"id": 1, "username": "ada", "password_hash": "h", "ldap_dn": "dn", "custom_data": {}})]
    csv_content = await export_table_to_csv(_FakeDB(rows), "users", columns=None, limit=10, current_user=None)
    header = csv_content.splitlines()[0]
    assert "password_hash" not in header
    assert "ldap_dn" not in header
    assert "custom_data" not in header
    assert header.startswith("id,username")


@pytest.mark.asyncio
async def test_export_table_to_csv_strips_secrets_even_when_requested(monkeypatch):
    cols = ["id", "username", "password_hash"]
    _patch_users_table(monkeypatch, cols)
    rows = [_FakeRow({"id": 1, "username": "ada", "password_hash": "h"})]
    # Even an explicit request for the secret column must not export it.
    csv_content = await export_table_to_csv(
        _FakeDB(rows), "users", columns=["id", "password_hash", "username"], limit=10, current_user=None
    )
    header = csv_content.splitlines()[0]
    assert "password_hash" not in header
    assert header == "id,username"


@pytest.mark.asyncio
async def test_export_table_to_csv_applies_field_rbac_when_user_given(monkeypatch):
    cols = ["id", "username", "password_hash"]
    _patch_users_table(monkeypatch, cols)
    rows = [_FakeRow({"id": 1, "username": "ada", "password_hash": "h"})]

    captured = {}

    async def fake_filter(db, user, table_name, results, action="view"):
        captured.update(user=user, table_name=table_name, results=results)
        return results

    monkeypatch.setattr(query_security_service, "filter_query_results", fake_filter)

    await export_table_to_csv(_FakeDB(rows), "users", columns=None, limit=10, current_user=_USER)

    # Field-level RBAC must be invoked with the caller + table when a user is given.
    assert captured.get("user") is _USER
    assert captured.get("table_name") == "users"


@pytest.mark.asyncio
async def test_export_table_to_csv_no_rbac_when_user_none(monkeypatch):
    cols = ["id", "username"]
    _patch_users_table(monkeypatch, cols)
    rows = [_FakeRow({"id": 1, "username": "ada"})]

    called = {"n": 0}

    async def fake_filter(*a, **k):
        called["n"] += 1
        return rows

    monkeypatch.setattr(query_security_service, "filter_query_results", fake_filter)
    await export_table_to_csv(_FakeDB(rows), "users", columns=None, limit=10, current_user=None)
    assert called["n"] == 0  # no user -> no RBAC call


# --------------------------------------------------------------------------- #
# export_query_to_csv
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_export_query_to_csv_strips_secrets(monkeypatch):
    async def fake_execute(db, table_name, filters=None, logic="AND", sort_by=None, sort_order="asc", limit=10000, offset=0):
        return {
            "items": [
                {"id": 1, "username": "ada", "password_hash": "s3cret", "ldap_dn": "cn=ada"},
                {"id": 2, "username": "linus", "password_hash": "pw", "ldap_dn": "cn=linus"},
            ],
            "total": 2, "limit": 100, "offset": 0,
        }

    monkeypatch.setattr(data_query_service, "execute_visual_query", fake_execute)
    csv_content = await export_query_to_csv(
        _FakeDB([]), "users", filters=None, current_user=None
    )
    lines = csv_content.splitlines()
    assert "password_hash" not in lines[0]
    assert "ldap_dn" not in lines[0]
    assert lines[0] == "id,username"
    # Data rows still present for the safe columns.
    assert lines[1] == "1,ada"
    assert lines[2] == "2,linus"


@pytest.mark.asyncio
async def test_export_query_to_csv_applies_field_rbac_when_user_given(monkeypatch):
    async def fake_execute(db, table_name, filters=None, logic="AND", sort_by=None, sort_order="asc", limit=10000, offset=0):
        return {"items": [{"id": 1, "username": "ada", "password_hash": "h"}], "total": 1, "limit": 1, "offset": 0}

    monkeypatch.setattr(data_query_service, "execute_visual_query", fake_execute)
    captured = {}

    async def fake_filter(db, user, table_name, results, action="view"):
        captured.update(user=user, table_name=table_name)
        return results

    monkeypatch.setattr(query_security_service, "filter_query_results", fake_filter)
    await export_query_to_csv(_FakeDB([]), "users", filters=None, current_user=_USER)
    assert captured.get("user") is _USER
    assert captured.get("table_name") == "users"


# --------------------------------------------------------------------------- #
# Endpoint-level RBAC
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_export_table_endpoint_returns_403_without_access(monkeypatch):
    from fastapi import HTTPException

    async def no_access(db, user, table_name, action="view"):
        return False

    monkeypatch.setattr(query_security_service, "validate_query_access", no_access)

    with pytest.raises(HTTPException) as exc:
        await data_export.export_table(
            table_name="users", columns=None, limit=10, current_user=_USER, db=None
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_export_query_endpoint_returns_403_without_access(monkeypatch):
    async def no_access(db, user, table_name, action="view"):
        return False

    monkeypatch.setattr(query_security_service, "validate_query_access", no_access)

    with pytest.raises(HTTPException) as exc:
        await data_export.export_query(
            query_body={"table": "users"}, current_user=_USER, db=None
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_export_table_endpoint_forwards_current_user(monkeypatch):
    async def yes_access(db, user, table_name, action="view"):
        return True

    monkeypatch.setattr(query_security_service, "validate_query_access", yes_access)

    captured = {}

    async def fake_export(db, table_name, columns=None, limit=10000, current_user=None):
        captured["current_user"] = current_user
        return "csv"

    monkeypatch.setattr(data_export, "export_table_to_csv", fake_export)
    resp = await data_export.export_table(
        table_name="users", columns=None, limit=10, current_user=_USER, db=None
    )
    assert captured["current_user"] is _USER
    assert resp.media_type == "text/csv"
