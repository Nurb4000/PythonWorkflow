"""
Regression tests for findings #12 (raw-SQL `/data-query/sql` path).

Two gaps were closed in ``execute_sql_query``:

* DoS: only a client-side ``asyncio.wait_for`` bounded query time, so
  ``SELECT pg_sleep(30)`` / unbounded joins held a pool slot for up to 30s.
  The endpoint now issues a server-side ``SET LOCAL statement_timeout`` so
  Postgres cancels heavy queries itself, and raises ``QueryTimeoutError``
  (mapped to HTTP 408) when SQLSTATE 57014 fires.

* Field filtering: the raw-SQL path returned every column with no
  field-level RBAC. For a simple single-table query the results are now trimmed
  to the caller's visible fields via ``filter_query_results``; complex
  (join/subquery) queries are intentionally left unfiltered.

These tests are self-contained (no live PostgreSQL): they use fake ``db`` /
``Result`` doubles and monkeypatch ``filter_query_results`` so the real code
paths are exercised without a database.
"""
import pytest

from app.services.data_query_service import (
    execute_sql_query,
    QueryTimeoutError,
    _extract_primary_table,
    _is_statement_timeout,
)


# --- pure helpers -------------------------------------------------------------

def test_extract_primary_table_simple():
    assert _extract_primary_table("SELECT * FROM users WHERE id = 1") == "users"
    assert _extract_primary_table("select username from configuration_items") == "configuration_items"


def test_extract_primary_table_complex_returns_none():
    # JOIN / subquery / no FROM -> cannot reliably map columns to one table.
    assert _extract_primary_table(
        "SELECT a.id, b.name FROM users a JOIN groups b ON a.gid = b.id"
    ) is None
    assert _extract_primary_table("SELECT * FROM (SELECT 1) x") is None
    assert _extract_primary_table("SELECT 1") is None


def test_is_statement_timeout_detects_57014():
    class AsyncpgCanceled:
        sqlstate = "57014"

    class Wrapped:
        orig = AsyncpgCanceled()

    assert _is_statement_timeout(Wrapped()) is True
    # Non-timeout SQLSTATE is not a timeout.
    class OtherOrig:
        sqlstate = "23505"

    class OtherWrapped:
        orig = OtherOrig()

    assert _is_statement_timeout(OtherWrapped()) is False
    # And when there is no .orig at all, it is not a timeout.
    assert _is_statement_timeout(RuntimeError("boom")) is False


# --- fake db / result doubles -------------------------------------------------

class FakeResult:
    def __init__(self, columns, rows):
        self._columns = columns
        self._rows = rows
        self.returns_rows = True

    def keys(self):
        return self._columns

    def fetchall(self):
        return self._rows


class FakeDB:
    """Records executed SQL; can be configured to raise on the query execute."""

    def __init__(self, query_result=None, query_exc=None):
        self.executed = []
        self.query_result = query_result
        self.query_exc = query_exc

    async def execute(self, stmt, params=None):
        self.executed.append(str(stmt))
        if params:
            self.executed.append(f"params={params}")
        if self.query_exc is not None:
            raise self.query_exc
        return self.query_result


def _timeout_exc():
    """Simulate asyncpg QueryCanceled (SQLSTATE 57014) wrapped by SQLAlchemy.

    The outer exception must derive from ``Exception`` (as a real DBAPIError does)
    and expose ``.orig`` pointing at the asyncpg error with ``sqlstate == 57014``.
    """
    class AsyncpgCanceled(Exception):
        sqlstate = "57014"

    class Wrapped(Exception):
        def __init__(self):
            self.orig = AsyncpgCanceled()

    return Wrapped()


# --- statement timeout emission -----------------------------------------------

async def test_emits_server_side_statement_timeout():
    db = FakeDB(query_result=FakeResult(["id"], [(1,)]))
    await execute_sql_query(db, "SELECT * FROM users", user=None)
    set_stmts = [s for s in db.executed if s.startswith("SET LOCAL statement_timeout")]
    assert len(set_stmts) == 1
    # The SET must be emitted before the actual query.
    assert db.executed.index(set_stmts[0]) < db.executed.index(
        [s for s in db.executed if "FROM users" in s][0]
    )


async def test_statement_timeout_ms_is_configurable():
    captured = {}

    class RecordingDB:
        async def execute(self, stmt, params=None):
            if str(stmt).startswith("SET LOCAL statement_timeout"):
                captured["params"] = params
            return FakeResult(["id"], [(1,)])

    await execute_sql_query(RecordingDB(), "SELECT 1", user=None, statement_timeout_ms=1234)
    # The timeout is passed as a bound parameter (driver renders :ms -> value).
    assert captured.get("params") == {"ms": 1234}


async def test_non_postgres_backend_continues_without_guard():
    class SetRaises:
        async def execute(self, stmt, params=None):
            if str(stmt).startswith("SET"):
                raise RuntimeError("syntax error")
            return FakeResult(["id"], [(1,)])

    db = SetRaises()
    out = await execute_sql_query(db, "SELECT * FROM users", user=None)
    assert out["total"] == 1


# --- cancellation -> QueryTimeoutError ----------------------------------------

async def test_statement_timeout_raises_query_timeout_error():
    db = FakeDB(query_exc=_timeout_exc())
    with pytest.raises(QueryTimeoutError):
        await execute_sql_query(db, "SELECT pg_sleep(30)", user=None)


async def test_non_timeout_error_propagates_plain():
    class OtherOrig:
        sqlstate = "23505"

    class OtherErr(Exception):
        def __init__(self):
            self.orig = OtherOrig()

    class DB:
        async def execute(self, stmt, params=None):
            raise OtherErr()

    with pytest.raises(Exception):
        await execute_sql_query(DB(), "SELECT 1", user=None)


# --- field filtering for single-table queries --------------------------------

async def test_field_filtering_applied_for_single_table(monkeypatch):
    import app.services.query_security_service as qss

    calls = {}

    class QS:
        async def filter_query_results(self, db, user, table, rows, action="view"):
            calls["table"] = table
            return [{"id": r["id"]} for r in rows]  # strip password_hash

    monkeypatch.setattr(qss, "query_security_service", QS())

    class User:
        role = "developer"

    db = FakeDB(query_result=FakeResult(["id", "password_hash"], [(1, "secret")]))
    out = await execute_sql_query(db, "SELECT id, password_hash FROM users", user=User())

    assert calls.get("table") == "users"
    assert set(out["items"][0].keys()) == {"id"}  # password_hash stripped


async def test_no_field_filtering_for_complex_query(monkeypatch):
    import app.services.query_security_service as qss

    calls = {}

    class QS:
        async def filter_query_results(self, db, user, table, rows, action="view"):
            calls["called"] = True
            return rows

    monkeypatch.setattr(qss, "query_security_service", QS())

    class User:
        role = "developer"

    db = FakeDB(query_result=FakeResult(["id"], [(1,)]))
    await execute_sql_query(
        db,
        "SELECT a.id FROM users a JOIN groups b ON a.gid = b.id",
        user=User(),
    )

    assert calls.get("called") is None  # complex query skipped filtering


# --- endpoint maps QueryTimeoutError -> 408 -----------------------------------

async def test_endpoint_returns_408_on_timeout(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import app.services.data_query_service as dqs
    from app.api import data_query as dq

    async def fake_execute(*a, **k):
        raise QueryTimeoutError("query exceeded 5000ms server-side statement timeout")

    monkeypatch.setattr(dq, "execute_sql_query", fake_execute)

    class FakeUser:
        role = "developer"

    async def fake_get_db():
        yield object()

    app = FastAPI()
    app.include_router(dq.router)
    app.dependency_overrides[dq.get_current_developer] = lambda: FakeUser()
    app.dependency_overrides[dq.get_db] = fake_get_db

    with TestClient(app) as client:
        resp = client.post("/sql", json={"sql": "SELECT pg_sleep(30)"})

    assert resp.status_code == 408
    assert "timeout" in resp.json()["detail"].lower()
