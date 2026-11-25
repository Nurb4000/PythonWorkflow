"""
Regression test for findings #23 (recomputed next_run_at was never persisted).

_add_schedule_job recomputed the next fire time from the resolved CronTrigger and
set schedule.next_run_at in memory but never committed it. During initialize() the
owning session closed before the write landed, so list_schedules returned a
stale/NULL "next run at".

Fix: persist the recomputed next_run_at inside _add_schedule_job by fetching the row
by id in a fresh session, setting next_run_at, and committing. _add_schedule_job /
add_schedule / update_schedule were made async to await the commit.

The test drives _add_schedule_job with a fake db_session_factory whose session records
what is committed, proving the recomputed next_run_at is persisted (was None before).
No real DB / event-loop nesting required.
"""
import asyncio

from datetime import datetime

from app.models.schemas import Schedule
from app.services.scheduler import SchedulerService


class _FakeSession:
    """Records the next_run_at value that gets committed. Async context manager."""

    def __init__(self, existing):
        self._existing = existing
        self.committed_next_run_at = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, model, pk):
        return self._existing

    async def commit(self):
        self.committed_next_run_at = self._existing.next_run_at


def _make_service(existing):
    svc = SchedulerService.__new__(SchedulerService)  # bypass __init__
    fake_session = _FakeSession(existing)

    # Mirrors async_sessionmaker(): called (not awaited) to yield a session CM.
    def make_factory():
        return fake_session

    svc.db_session_factory = make_factory
    # Minimal scheduler stub: add_job/remove_job no-ops, get_job returns nothing.
    sched = type("S", (), {
        "add_job": lambda self, *a, **k: None,
        "remove_job": lambda self, *a, **k: None,
        "get_job": lambda self, *a, **k: None,
    })()
    svc.scheduler = sched
    return svc, fake_session


def test_next_run_at_is_persisted():
    existing = Schedule(workflow_id=1, cron_expression="0 0 * * *", is_enabled=True)
    existing.next_run_at = None  # simulate the stale/NULL value before the fix

    svc, fake_session = _make_service(existing)

    asyncio.run(svc._add_schedule_job(existing))

    # The recomputed next fire time must have been committed to the DB.
    assert fake_session.committed_next_run_at is not None
    assert isinstance(fake_session.committed_next_run_at, datetime)


def test_add_schedule_and_update_schedule_are_async():
    # Both wrappers must be awaitable and forward to _add_schedule_job.
    existing = Schedule(workflow_id=1, cron_expression="0 0 * * *", is_enabled=True)
    svc, fake_session = _make_service(existing)

    assert asyncio.iscoroutinefunction(svc.add_schedule)
    assert asyncio.iscoroutinefunction(svc.update_schedule)

    asyncio.run(svc.add_schedule(existing))
    assert fake_session.committed_next_run_at is not None

    existing.next_run_at = None
    asyncio.run(svc.update_schedule(existing))
    assert fake_session.committed_next_run_at is not None
