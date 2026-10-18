"""
Regression tests for ``WorkflowRun.duration_seconds``.

Root cause: ``started_at``/``completed_at`` are ``timestamptz`` columns, but they
are inserted with *mixed* timezone flavors across the codebase. ``started_at`` is
set with naive ``datetime.utcnow()`` (engine L470/L574), while ``completed_at`` is
sometimes set tz-aware — via ``func.now()`` (a DB-side SQL function) in
``workflow_runs.py`` and via ``datetime.now(timezone.utc)`` in the timeout path
(``_check_timeout`` L443).

This driver round-trips flavor faithfully: a naive value loads back naive, an
aware value loads back aware. So a run that *timed out* ends up with a naive
``started_at`` and an aware ``completed_at``. Any direct subtraction of the two
(``admin.py`` `/stats` avg-duration, ``step_executors.py`` sub-workflow duration)
then raised ``TypeError: can't subtract offset-naive and offset-aware
datetimes``.

The fix centralizes normalization in ``WorkflowRun.duration_seconds``, which
coerces both operands to UTC before subtracting.
"""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

import pytest

from app.models.schemas import WorkflowRun


async def _reload(db_session, run_id):
    return (await db_session.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))).scalar_one()


@pytest.mark.asyncio
async def test_duration_seconds_normalizes_mixed_flavors(db_session):
    """The exact timed-out-run shape: started_at naive, completed_at aware.

    This must not raise TypeError and must return ~120s."""
    now_aware = datetime.now(timezone.utc)
    run = WorkflowRun(
        status="timeout",
        started_at=datetime.utcnow() - timedelta(seconds=120),  # naive
        completed_at=now_aware,                                  # aware
    )
    db_session.add(run)
    await db_session.commit()

    run_id = run.id
    # Reload from the DB so both timestamps come back with their stored flavor.
    reloaded = await _reload(db_session, run_id)

    # Before the fix this line raised TypeError; now it normalizes both to UTC.
    duration = reloaded.duration_seconds
    assert duration is not None
    assert 119.0 <= duration <= 121.0


@pytest.mark.asyncio
async def test_duration_seconds_none_when_incomplete(db_session):
    run = WorkflowRun(status="running", started_at=datetime.utcnow())
    db_session.add(run)
    await db_session.commit()

    reloaded = await _reload(db_session, run.id)
    assert reloaded.duration_seconds is None


@pytest.mark.asyncio
async def test_duration_seconds_both_naive(db_session):
    """Legacy shape where both timestamps are naive still works."""
    run = WorkflowRun(
        status="completed",
        started_at=datetime.utcnow() - timedelta(seconds=30),
        completed_at=datetime.utcnow(),
    )
    db_session.add(run)
    await db_session.commit()

    reloaded = await _reload(db_session, run.id)
    assert 29.0 <= reloaded.duration_seconds <= 31.0
