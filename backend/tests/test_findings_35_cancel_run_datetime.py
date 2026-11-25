"""
Regression tests for findings #35 (db.func.now() assigned to a mapped column -> HTTP 500).

Two endpoints assigned a SQLAlchemy ``func.now()`` SQL expression directly to a
mapped ``DateTime(timezone=True)`` column attribute and then committed:

    run.completed_at = db.func.now()          # app/api/workflow_runs.py (cancel_run)
    field.deprecated_at = func.now()          # app/api/field_library.py (deprecate_field)

Assigning the SQL expression to the mapped attribute makes SQLAlchemy bind it as a
*parameter value* in the UPDATE. asyncpg cannot serialize a SQL expression as a
bound parameter, so ``await db.commit()`` raises -> HTTP 500.

Fix (#35): assign a tz-aware Python datetime (``datetime.now(timezone.utc)``), which
matches the ``DateTime(timezone=True)`` column and serializes cleanly.

These tests are self-contained: in-memory SQLite (StaticPool) with just the relevant
table, so no live PostgreSQL is required. The same bind-as-parameter footgun also
fails under SQLite's driver, so reintroducing ``func.now()`` is caught by the commit
assertion; tz-awareness of the assigned value is verified by construction via a
monkeypatched ``datetime.now``.
"""
import datetime as dt

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.api.workflow_runs as workflow_runs_api
from app.core.database import Base
from app.models.schemas import WorkflowRun
from app.models.field_library import FieldDefinition
from app.api.workflow_runs import cancel_run
from app.api.field_library import deprecate_field_definition


@pytest.fixture()
async def sqlite():
    """In-memory SQLite with just the workflow_runs table; returns a session factory."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[WorkflowRun.__table__])

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture()
async def sqlite_fields():
    """In-memory SQLite with just the field_definitions table; returns a factory."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[FieldDefinition.__table__])

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


class _FakeUser:
    """Minimal user; role 'admin' short-circuits workflow access checks."""

    def __init__(self, role="admin", uid=1):
        self.role = role
        self.id = uid


async def _insert_run(factory, run_id, status):
    async with factory() as db:
        db.add(WorkflowRun(id=run_id, workflow_id=1, status=status))
        await db.commit()


async def test_cancel_run_assigns_tz_aware_utc_now(sqlite, monkeypatch):
    """The fix calls datetime.now(timezone.utc) — tz-aware by construction.

    ``datetime`` is an immutable builtin, so we replace the module-level name with a
    shim that records the tz argument and delegates to the real class. (Line 206's
    ``datetime.utcnow()`` uses its own local import, so it is unaffected.)
    """
    real_datetime = dt.datetime
    seen_tz = []

    class _DatetimeShim:
        @staticmethod
        def now(tz=None):
            seen_tz.append(tz)
            return real_datetime.now(tz)

    monkeypatch.setattr(workflow_runs_api, "datetime", _DatetimeShim)

    await _insert_run(sqlite, run_id=42, status="running")
    async with sqlite() as db:
        result = await cancel_run(
            workflow_id=1,
            run_id=42,
            current_user=_FakeUser(),
            db=db,
        )

    assert result == {"message": "Run cancelled successfully"}
    # The assignment used a tz-aware UTC clock, matching DateTime(timezone=True).
    assert seen_tz == [dt.timezone.utc]


async def test_cancel_run_succeeds_and_sets_completed_at(sqlite):
    """Cancelling a running run returns 200 and stamps a real tz-aware datetime."""
    await _insert_run(sqlite, run_id=42, status="running")

    async with sqlite() as db:
        result = await cancel_run(
            workflow_id=1,
            run_id=42,
            current_user=_FakeUser(),
            db=db,
        )

    assert result == {"message": "Run cancelled successfully"}

    # Persisted state: status flipped and completed_at is a live datetime ~now.
    # (SQLite has no timezone concept and returns naive datetimes on read-back, so we
    # normalize to UTC before comparing; tz-awareness of the assigned value is proven
    # by construction in test_cancel_run_assigns_tz_aware_utc_now.)
    async with sqlite() as db:
        row = (await db.execute(select(WorkflowRun).where(WorkflowRun.id == 42))).scalar_one()
        assert row.status == "cancelled"
        assert isinstance(row.completed_at, dt.datetime)
        persisted = row.completed_at
        if persisted.tzinfo is None:
            persisted = persisted.replace(tzinfo=dt.timezone.utc)
        # A live assignment: completed_at is ~now, not None/stale. This catches a
        # regression where someone assigns func.now() (commit 500s) or a fixed value.
        delta = abs((persisted - dt.datetime.now(dt.timezone.utc)).total_seconds())
        assert delta < 30


async def test_cancel_run_rejects_terminal_runs(sqlite):
    """A completed run cannot be cancelled (regression guard on the status gate)."""
    await _insert_run(sqlite, run_id=7, status="completed")

    async with sqlite() as db:
        with pytest.raises(Exception):
            await cancel_run(
                workflow_id=1,
                run_id=7,
                current_user=_FakeUser(),
                db=db,
            )


async def test_cancel_missing_run_returns_404(sqlite):
    """Cancelling a non-existent run raises 404 (not a DB error)."""
    async with sqlite() as db:
        with pytest.raises(Exception):
            await cancel_run(
                workflow_id=1,
                run_id=999,
                current_user=_FakeUser(),
                db=db,
            )


async def test_deprecate_field_succeeds_and_sets_deprecated_at(sqlite_fields):
    """The same db.func.now() footgun in deprecate_field is fixed (no HTTP 500).

    ``field.deprecated_at = func.now()`` assigned a SQL expression to the mapped
    DateTime(timezone=True) column, so commit raised under asyncpg. Now it stamps a
    real datetime and returns 200.
    """
    async with sqlite_fields() as db:
        db.add(FieldDefinition(key="cost_center", label="Cost Center"))
        await db.commit()

    async with sqlite_fields() as db:
        result = await deprecate_field_definition(
            field_id=1,
            current_user=_FakeUser(role="admin"),
            db=db,
        )

    assert result == {"message": "Field definition deprecated", "id": 1}

    async with sqlite_fields() as db:
        row = (await db.execute(select(FieldDefinition).where(FieldDefinition.id == 1))).scalar_one()
        assert row.is_deprecated is True
        assert row.is_active is False
        assert isinstance(row.deprecated_at, dt.datetime)
